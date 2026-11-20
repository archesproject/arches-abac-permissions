from functools import cache
import copy
import json
from urllib.parse import parse_qsl

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from arches.app.models.models import (
    GraphModel,
    NodeGroup,
    ResourceInstance,
    SearchComponent,
)
from arches.app.models.system_settings import settings
from arches.app.search.components.base import SearchFilterFactory
from arches.app.search.elasticsearch_dsl_builder import Bool, Ids, Query, Terms
from arches.app.search.mappings import RESOURCES_INDEX
from arches.app.search.search_engine_factory import SearchEngineFactory
from arches_abac_permissions.models import InclusionRule
from arches_abac_permissions.rule_types import RuleType, elasticsearch_enabled

# Compiled queries by search, each with the resource models it was compiled
# against: publishing or (de)activating a model changes how a search compiles.
COMPILED = {}

# Search components that narrow results. Paging, sorting and the searching
# user's permissions are not part of a rule.
FILTER_COMPONENTS = (
    "advanced-search",
    "ids",
    "lifecycle-state-filter",
    "map-filter",
    "resource-type-filter",
    "term-filter",
    "time-filter",
)
# Search parameters a filter component reads from the request, not a component.
FILTER_SETTINGS = ("language",)
# Core search components that only page, sort or display results. Any other
# component a search uses is refused, so a rule never quietly drops a filter.
IGNORED_COMPONENTS = (
    "paging-filter",
    "related-resources-filter",
    "saved-searches",
    "search-export",
    "search-results",
    "sort-results",
    "standard-search-view",
)


class ElasticsearchRule(InclusionRule):
    """
    Rule matching the resources a core Arches search finds.

    definition: {"query_string": "<the search page's URL, or its query string>"}

    The search is compiled to Elasticsearch each time the rule is used, as a
    superuser would run it, with provisional data left out. Only
    ``FILTER_COMPONENTS`` are applied.
    """

    rule_type = RuleType(
        key="elasticsearch",
        label=gettext_lazy("Resource is found by Elasticsearch"),
        description=gettext_lazy(
            "Matches the resources a search of the search page finds"
        ),
        icon="pi pi-search",
        definition_keys=("query_string",),
        requires_elasticsearch=True,
    )

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        return False

    # One request checks a record against every rule that sets this.
    evaluated_in_es = True

    @classmethod
    def get_search_filter(cls, inclusion_rule):
        params = cls.parse_definition(inclusion_rule.definition)
        key = json.dumps(params, sort_keys=True)
        models = get_resource_models()
        compiled_for, query = COMPILED.get(key, (None, None))
        if compiled_for != models:
            query = cls.compile(params)
            COMPILED[key] = (models, query)
        check_narrows(query)
        active = [str(pk) for pk, _publication, is_active in models if is_active]
        # Callers may add to the filter they get, so never hand out the cached
        # one. The search page only shows resources of active models.
        return (
            Bool()
            .filter(copy.deepcopy(query))
            .filter(Terms(field="graph_id", terms=active))
        )

    @classmethod
    def compile(cls, params):
        """Return the Elasticsearch query for a search's filter parameters."""
        request = RequestFactory().get("/search", params)
        # Unsaved, so it has every permission without touching the database.
        request.user = User(username="abac rule", is_superuser=True, is_active=True)
        filter_factory = SearchFilterFactory(request, request.user)
        all_nodegroups = [
            str(pk) for pk in NodeGroup.objects.values_list("pk", flat=True)
        ]
        query = Query(SearchEngineFactory().create())
        search_query_object = {"query": query}
        for componentname, querystring in params.items():
            if componentname in FILTER_SETTINGS:
                continue
            search_filter = filter_factory.get_filter(componentname)
            if search_filter is None:
                raise ValidationError(
                    _("This Arches has no %s search filter.") % componentname
                )
            search_filter.append_dsl(
                search_query_object,
                permitted_nodegroups=all_nodegroups,
                include_provisional=False,
                querystring=querystring,
            )
        return query.dsl["query"]

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        return ResourceInstance.objects.filter(
            pk__in=search_resource_ids(cls.get_search_filter(inclusion_rule))
        )

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        query = Query(SearchEngineFactory().create(), start=0, limit=0)
        query.add_query(
            Bool()
            .filter(Ids(ids=[str(resource.pk)]))
            .filter(cls.get_search_filter(inclusion_rule))
        )
        return query.search(index=RESOURCES_INDEX)["hits"]["total"]["value"] > 0

    @classmethod
    def validate_definition(cls, inclusion_rule):
        try:
            query = cls.compile(cls.parse_definition(inclusion_rule.definition))
            check_narrows(query)
            check_runs(query)
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(_("The search can't be run: %s") % e)

    @staticmethod
    def parse_definition(definition):
        if not elasticsearch_enabled():
            raise ValidationError(_("Elasticsearch is turned off."))
        query_string = definition.get("query_string")
        if not isinstance(query_string, str):
            raise ValidationError(_("Search rules require a 'query_string'."))
        pairs = parse_qsl(query_string.split("?", 1)[-1])
        unknown = sorted(
            {
                key
                for key, _value in pairs
                if key in get_search_component_names()
                and key not in FILTER_COMPONENTS + IGNORED_COMPONENTS
            }
        )
        if unknown:
            raise ValidationError(
                _("The search uses %s, which a rule can't apply.") % ", ".join(unknown)
            )
        params = {
            key: value
            for key, value in pairs
            if key in FILTER_COMPONENTS + FILTER_SETTINGS
        }
        if not any(key in FILTER_COMPONENTS for key in params):
            raise ValidationError(
                _("The search must use at least one of: %s.")
                % ", ".join(FILTER_COMPONENTS)
            )
        return params

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"


def narrows(dsl):
    if "bool" in dsl:
        return any(
            narrows(clause)
            for occurrence in ("filter", "must", "should", "must_not")
            for clause in dsl["bool"].get(occurrence, [])
        )
    if "nested" in dsl:
        return narrows(dsl["nested"]["query"])
    return "match_all" not in dsl


def check_narrows(query):
    # A search can stop narrowing after it was saved (a resource model
    # changes), so this runs on every use, not only when saving.
    if not narrows(query):
        raise ValidationError(_("The search doesn't restrict any records."))


def check_runs(search_filter):
    # Elasticsearch refuses some searches that compile, like a term "castle* AND".
    query = Query(SearchEngineFactory().create(), start=0, limit=0)
    query.add_query(search_filter)
    if query.search(index=RESOURCES_INDEX) is None:
        raise ValidationError(_("Elasticsearch can't run the search."))


@cache
def get_search_component_names():
    return set(SearchComponent.objects.values_list("componentname", flat=True))


def get_resource_models():
    return list(
        GraphModel.objects.filter(isresource=True, source_identifier=None)
        .order_by("pk")
        .values_list("pk", "publication_id", "is_active")
    )


def search_resource_ids(search_filter) -> list[str]:
    """Return the ids of every indexed resource matching ``search_filter``."""
    search_engine = SearchEngineFactory().create()
    query = Query(search_engine, start=0, limit=settings.SEARCH_RESULT_LIMIT)
    query.add_query(search_filter)
    query.include("resourceinstanceid")
    results = query.search(index=RESOURCES_INDEX, scroll="1m")
    hits = results["hits"]["hits"]
    while len(hits) < results["hits"]["total"]["value"]:
        page = search_engine.es.scroll(scroll_id=results["_scroll_id"], scroll="1m")
        if not page["hits"]["hits"]:
            break
        hits += page["hits"]["hits"]
    return [hit["_id"] for hit in hits]
