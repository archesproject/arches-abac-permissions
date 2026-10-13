from arches.app.models.models import Node
from arches.app.models.system_settings import settings
from arches.app.search.elasticsearch_dsl_builder import (
    Aggregation,
    Bool,
    Match,
    Nested,
    Query,
    Term,
    Terms,
)
from arches.app.search.mappings import RESOURCES_INDEX
from arches.app.search.search_engine_factory import SearchEngineFactory
from arches.app.search.search_term import TermSearch
from arches.app.utils.permission_backend import (
    get_nodegroups_by_perm,
    get_permission_search_filter,
    user_is_resource_reviewer,
)


class PermittedTermSearch:
    """
    Core's TermSearch reads the terms index, which has no resource permissions, so it
    suggests values from resources the user can't see. This searches resources instead.
    """

    @staticmethod
    def search_terms(search_string, lang, user, term_search_type):
        if user.is_superuser:
            return TermSearch.search_terms(search_string, lang, user, term_search_type)

        search_string = search_string.lower()
        matching_strings = Bool()
        if lang != "*":
            matching_strings.must(Term(field="strings.language", term=lang))
        matching_strings.should(
            Match(field="strings.string", query=search_string, type="phrase_prefix")
        )
        matching_strings.should(
            Match(
                field="strings.string.folded", query=search_string, type="phrase_prefix"
            )
        )
        matching_strings.should(
            Match(
                field="strings.string.folded",
                query=search_string,
                fuzziness="AUTO",
                prefix_length=settings.SEARCH_TERM_SENSITIVITY,
            )
        )
        permitted_nodegroups = get_nodegroups_by_perm(user, "models.read_nodegroup")
        matching_strings.filter(
            Terms(
                field="strings.nodegroup_id",
                terms=[str(nodegroup) for nodegroup in permitted_nodegroups],
            )
        )
        if not user_is_resource_reviewer(user):
            matching_strings.filter(Terms(field="strings.provisional", terms=["false"]))

        query = Query(SearchEngineFactory().create(), start=0, limit=0)
        resources = Bool()
        resources.filter(Nested(path="strings", query=matching_strings))
        resources.filter(get_permission_search_filter(user))
        query.add_query(resources)

        strings_agg = Aggregation(name="strings", type="nested", path="strings")
        matching_agg = Aggregation(name="matching", type="filter")
        matching_agg.agg["matching"]["filter"] = matching_strings.dsl
        value_agg = Aggregation(
            name="value_agg",
            type="terms",
            field="strings.string.raw",
            size=settings.SEARCH_DROPDOWN_LENGTH,
        )
        value_agg.add_aggregation(
            Aggregation(name="nodegroupid", type="terms", field="strings.nodegroup_id")
        )
        matching_agg.add_aggregation(value_agg)
        strings_agg.add_aggregation(matching_agg)
        query.add_aggregation(strings_agg)

        results = query.search(index=RESOURCES_INDEX)
        if results is None:
            return []
        buckets = results["aggregations"]["strings"]["matching"]["value_agg"]["buckets"]

        nodegroup_ids = {
            nodegroup["key"]
            for bucket in buckets
            for nodegroup in bucket["nodegroupid"]["buckets"]
        }
        node_lookup = {
            str(node.nodeid): f"{node.graph.name} - {node.name}"
            for node in Node.objects.filter(nodeid__in=nodegroup_ids).select_related(
                "graph"
            )
        }
        suggestions = []
        for bucket in buckets:
            for nodegroup in bucket["nodegroupid"]["buckets"]:
                suggestions.append(
                    {
                        "type": "term",
                        "context": "",
                        "context_label": node_lookup.get(nodegroup["key"], " - "),
                        "id": f'{term_search_type["key"]}{len(suggestions)}',
                        "text": bucket["key"],
                        "value": bucket["key"],
                        "nodegroupid": nodegroup["key"],
                    }
                )
        return suggestions
