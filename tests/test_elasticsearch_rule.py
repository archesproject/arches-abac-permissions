import json
from unittest import mock, skipUnless
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.test import override_settings

from arches.app.models.models import GraphModel, SearchComponent
from arches.app.search.mappings import RESOURCES_INDEX
from arches.app.search.search_engine_factory import SearchEngineFactory
from arches_abac_permissions.rules import elasticsearch_rule
from arches_abac_permissions.rules.elasticsearch_rule import (
    ElasticsearchRule,
    get_search_component_names,
    narrows,
)
from tests.test_inclusion_rules import LifecycleTestCase, make_rule
from tests.test_search_filters import dsl, elasticsearch_available


def make_elasticsearch_rule(**params):
    query_string = urlencode({key: json.dumps(value) for key, value in params.items()})
    return make_rule(
        modulename="elasticsearch_rule.py",
        classname="ElasticsearchRule",
        definition={"query_string": query_string},
    )


class ElasticsearchRuleTestCase(LifecycleTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Search leaves out resources of inactive models.
        GraphModel.objects.filter(pk=cls.graph.pk).update(is_active=True)

    def graph_rule(self):
        return make_elasticsearch_rule(
            **{
                "resource-type-filter": [
                    {"graphid": str(self.graph.pk), "inverted": False}
                ]
            }
        )


# Running a search needs Elasticsearch; ElasticsearchRuleSearchTests covers it.
@mock.patch.object(elasticsearch_rule, "check_runs", mock.Mock())
class ElasticsearchRuleTests(ElasticsearchRuleTestCase):
    def test_get_class_module(self):
        self.assertIs(self.graph_rule().get_class_module(), ElasticsearchRule)

    def test_search_filter_comes_from_the_search_components(self):
        self.assertIn(
            {"terms": {"graph_id": [str(self.graph.pk)]}},
            dsl(self.graph_rule().get_search_filter_for_rule())["bool"]["filter"][0][
                "bool"
            ]["filter"],
        )

    def test_keeps_only_filtering_components(self):
        params = ElasticsearchRule.parse_definition(
            {
                "query_string": "http://example.org/search"
                "?term-filter=%5B%5D&paging-filter=2&sort-results=asc&language=en"
            }
        )
        self.assertEqual(params, {"term-filter": "[]", "language": "en"})

    def test_searches_in_the_search_language(self):
        rule = make_elasticsearch_rule(
            **{
                "term-filter": [
                    {"type": "string", "value": "castle", "inverted": False}
                ]
            }
        )
        self.assertNotIn(
            "strings.language", json.dumps(dsl(rule.get_search_filter_for_rule()))
        )
        rule.definition["query_string"] += "&language=en"
        self.assertIn(
            "strings.language", json.dumps(dsl(rule.get_search_filter_for_rule()))
        )

    def test_leaves_out_resources_of_inactive_models(self):
        rule = make_elasticsearch_rule(ids=[str(self.matching.pk)])
        active = dsl(rule.get_search_filter_for_rule())["bool"]["filter"][1]
        self.assertIn(str(self.graph.pk), active["terms"]["graph_id"])
        GraphModel.objects.filter(pk=self.graph.pk).update(is_active=False)
        active = dsl(rule.get_search_filter_for_rule())["bool"]["filter"][1]
        self.assertNotIn(str(self.graph.pk), active["terms"]["graph_id"])

    def test_a_nested_search_must_restrict_too(self):
        self.assertFalse(narrows({"nested": {"path": "tiles", "query": {"bool": {}}}}))
        self.assertTrue(
            narrows({"nested": {"path": "tiles", "query": {"term": {"a": "b"}}}})
        )

    @override_settings(ELASTICSEARCH_ENABLED=False)
    def test_refused_without_elasticsearch(self):
        rule = self.graph_rule()
        with self.assertRaisesMessage(ValidationError, "Elasticsearch is turned off"):
            rule.clean()
        with self.assertRaisesMessage(ValidationError, "Elasticsearch is turned off"):
            rule.get_search_filter_for_rule()

    def test_valid_definition(self):
        self.graph_rule().clean()

    def test_refuses_search_components_it_cannot_apply(self):
        SearchComponent.objects.create(
            name="Custom",
            icon="",
            type="custom-filter-type",
            componentpath="views/components/search/custom-filter",
            componentname="custom-filter",
        )
        get_search_component_names.cache_clear()
        self.addCleanup(get_search_component_names.cache_clear)
        rule = self.graph_rule()
        rule.definition["query_string"] += "&custom-filter=x"
        with self.assertRaisesMessage(ValidationError, "uses custom-filter"):
            rule.clean()

    def test_refuses_the_provisional_filter(self):
        rule = self.graph_rule()
        rule.definition["query_string"] += "&provisional-filter=x"
        with self.assertRaisesMessage(ValidationError, "uses provisional-filter"):
            rule.clean()

    def test_invalid_definitions(self):
        for query_string, message in (
            (None, "require a 'query_string'"),
            ("", "at least one of"),
            ("paging-filter=1", "at least one of"),
            ("term-filter=%5B%5D", "doesn't restrict any records"),
            ("term-filter=not-json", "can't be run"),
        ):
            with self.subTest(query_string=query_string):
                rule = make_rule(
                    modulename="elasticsearch_rule.py",
                    classname="ElasticsearchRule",
                    definition={"query_string": query_string},
                )
                with self.assertRaisesMessage(ValidationError, message):
                    rule.clean()


@skipUnless(elasticsearch_available(), "Elasticsearch is not available")
class ElasticsearchRuleSearchTests(ElasticsearchRuleTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        se = SearchEngineFactory().create()
        cls.indexed = (cls.matching, cls.other_graph_active)
        for resource in cls.indexed:
            se.index_data(
                index=RESOURCES_INDEX,
                id=str(resource.pk),
                body={
                    "resourceinstanceid": str(resource.pk),
                    "graph_id": str(resource.graph_id),
                },
            )
        se.refresh(index=RESOURCES_INDEX)

    @classmethod
    def tearDownClass(cls):
        se = SearchEngineFactory().create()
        for resource in cls.indexed:
            se.delete(index=RESOURCES_INDEX, id=str(resource.pk))
        super().tearDownClass()

    def test_matches_what_search_finds(self):
        rule = self.graph_rule()
        self.assertEqual(set(rule.get_matching_resources()), {self.matching})
        self.assertTrue(rule.matches_resource(self.matching))
        self.assertFalse(rule.matches_resource(self.other_graph_active))
        # Matching follows the index, so unindexed resources never match.
        self.assertFalse(rule.matches_resource(self.also_matching))

    def test_refuses_a_search_elasticsearch_cannot_run(self):
        rule = make_elasticsearch_rule(
            **{
                "term-filter": [
                    {"type": "string", "value": "castle* AND", "inverted": False}
                ]
            }
        )
        with self.assertRaisesMessage(ValidationError, "can't run the search"):
            rule.clean()
