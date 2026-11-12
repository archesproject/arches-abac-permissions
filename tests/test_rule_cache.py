import uuid

from celery.signals import task_postrun, task_prerun
from django.core.signals import request_finished, request_started
from django.core.exceptions import ValidationError
from django.db import connection
from django.urls import reverse
from django.test.utils import CaptureQueriesContext

from arches_abac_permissions import rule_cache
from arches_abac_permissions.rule_cache import rule_definition_cache
from arches_abac_permissions.rules.tile_node_value_rule import TileNodeValueRule
from tests.test_inclusion_rules import make_rule
from tests.test_spatial_rule import SpatialTestCase
from tests.test_tile_node_value_rule import TileNodeValueTestCase
from tests.test_views import ApiTestCase

MATCH_QUERIES = 1


def count_queries(callable_):
    with CaptureQueriesContext(connection) as context:
        result = callable_()
    return result, len(context)


class RuleCacheAssertions:
    expected_match_queries = MATCH_QUERIES

    def make_rule_under_test(self):
        raise NotImplementedError

    def assertCacheEffective(self, rule, hit, miss):
        _, first_uncached = count_queries(lambda: rule.matches_resource(hit))
        _, second_uncached = count_queries(lambda: rule.matches_resource(hit))
        self.assertEqual(first_uncached, second_uncached)
        with rule_definition_cache():
            rule.matches_resource(hit)
            result, queries = count_queries(lambda: rule.matches_resource(hit))
            self.assertTrue(result)
            self.assertEqual(queries, self.expected_match_queries)
            self.assertFalse(rule.matches_resource(miss))
        self.assertGreater(second_uncached, queries)
        self.assertTrue(rule.matches_resource(hit))
        self.assertFalse(rule.matches_resource(miss))

    def test_repeat_calls_skip_parsing(self):
        self.assertCacheEffective(self.make_rule_under_test(), self.hit, self.miss)


class LifecycleQueryTests(TileNodeValueTestCase):
    def make_lifecycle_rule(self, **overrides):
        definition = {
            "graphid": str(self.graph.pk),
            "lifecycle_state_id": str(self.active_state.pk),
            **overrides,
        }
        return make_rule(
            modulename="lifecycle_state_rule.py",
            classname="LifecycleStateRule",
            definition=definition,
        )

    def test_evaluation_needs_no_lookups(self):
        rule = self.make_lifecycle_rule()
        draft = self.make_resource(self.graph, self.draft_state)
        with self.assertNumQueries(0):
            self.assertTrue(rule.matches_resource(self.hit))
            self.assertFalse(rule.matches_resource(draft))
            rule.get_matching_resources()
        self.assertIn(self.hit, rule.get_matching_resources())
        self.assertNotIn(draft, rule.get_matching_resources())

    def test_search_url_needs_no_lookups(self):
        rule = self.make_lifecycle_rule()
        with self.assertNumQueries(0):
            url = rule.get_search_rule_url()
        self.assertIn(str(self.active_state.pk), url)

    def test_invalid_ids_match_nothing(self):
        for overrides in (
            {"graphid": "nope"},
            {"lifecycle_state_id": None},
            {"lifecycle_state_id": 5},
        ):
            rule = self.make_lifecycle_rule(**overrides)
            self.assertFalse(rule.matches_resource(self.hit))
            self.assertEqual(list(rule.get_matching_resources()), [])
        rule = self.make_lifecycle_rule()
        rule.definition = {}
        self.assertFalse(rule.matches_resource(self.hit))
        self.assertEqual(list(rule.get_matching_resources()), [])

    def test_validation_rejects_state_of_other_lifecycle(self):
        rule = self.make_lifecycle_rule(
            lifecycle_state_id=str(self.other_lifecycle_state.pk)
        )
        with self.assertRaises(ValidationError):
            rule.clean()


class SpatialQueryTests(SpatialTestCase):
    def test_evaluation_only_runs_the_match_query(self):
        rule = self.make_spatial_rule()
        with self.assertNumQueries(1):
            self.assertTrue(rule.matches_resource(self.inside))
        with self.assertNumQueries(1):
            self.assertFalse(rule.matches_resource(self.outside))
        with self.assertNumQueries(0):
            rule.get_matching_resources()
        self.assertEqual(
            set(rule.get_matching_resources()), {self.inside, self.crossing}
        )

    def test_other_graph_needs_no_query(self):
        rule = self.make_spatial_rule()
        with self.assertNumQueries(0):
            self.assertFalse(rule.matches_resource(self.other_graph_active))

    def test_validation_rejects_bad_references(self):
        for overrides in (
            {"graphid": str(self.other_graph.pk)},
            {"nodeid": str(self.string_node.pk)},
            {"nodeid": str(uuid.uuid4())},
            {"graphid": str(uuid.uuid4())},
            {"graphid": "nope"},
            {"nodeid": "nope"},
        ):
            with self.subTest(overrides=overrides):
                rule = self.make_spatial_rule()
                rule.definition.update(overrides)
                with self.assertRaises(ValidationError):
                    rule.clean()
                if "nope" in overrides.values():
                    with self.assertRaises(ValidationError):
                        rule.matches_resource(self.inside)


class TileCacheTests(RuleCacheAssertions, TileNodeValueTestCase):
    def make_rule_under_test(self):
        return self.make_value_rule("string", "hola")

    def test_parse_definition_is_one_query(self):
        rule = self.make_value_rule("number", 5)
        with self.assertNumQueries(1):
            TileNodeValueRule.parse_definition(rule.definition)
        for definition, message in (
            ({"graphid": str(uuid.uuid4())}, "is not the id of a resource model"),
            ({"nodeid": str(uuid.uuid4())}, "is not the id of a node"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesMessage(ValidationError, message):
                    TileNodeValueRule.parse_definition(
                        {**rule.definition, **definition}
                    )

    def test_any_language_skips_language_query(self):
        rule = self.make_rule_under_test()
        with rule_definition_cache():
            rule.matches_resource(self.hit)
            with CaptureQueriesContext(connection) as context:
                rule.matches_resource(self.hit)
        self.assertFalse(any("languages" in query["sql"] for query in context))

    def test_definition_change_is_not_stale(self):
        rule = self.make_rule_under_test()
        with rule_definition_cache():
            self.assertTrue(rule.matches_resource(self.hit))
            rule.definition["value"] = "nothing"
            self.assertFalse(rule.matches_resource(self.hit))

    def test_get_matching_resources_uses_cache(self):
        rule = self.make_rule_under_test()
        _, uncached = count_queries(lambda: list(rule.get_matching_resources()))
        with rule_definition_cache():
            rule.get_matching_resources()
            matching, cached = count_queries(lambda: set(rule.get_matching_resources()))
        self.assertEqual(matching, {self.hit})
        self.assertLess(cached, uncached)

    def test_validation_error_not_cached(self):
        rule = make_rule(
            modulename="tile_node_value_rule.py",
            classname="TileNodeValueRule",
            definition=self.definition("missing-node", "x"),
        )
        with rule_definition_cache():
            for _ in range(2):
                with self.assertRaises(ValidationError):
                    rule.matches_resource(self.hit)
            self.assertEqual(rule_cache._cache.get(), {})


class RuleCacheScopeTests(ApiTestCase):
    def assertInactive(self):
        self.assertIsNone(rule_cache._cache.get())

    def test_inactive_by_default(self):
        self.assertInactive()

    def test_nested_keeps_outer_cache(self):
        with rule_definition_cache():
            rule_cache._cache.get()["marker"] = 1
            with rule_definition_cache():
                self.assertEqual(rule_cache._cache.get(), {"marker": 1})
            self.assertEqual(rule_cache._cache.get(), {"marker": 1})
        self.assertInactive()

    def test_signals(self):
        for start, finish in (
            (request_started, request_finished),
            (task_prerun, task_postrun),
        ):
            start.send(sender=None)
            self.assertEqual(rule_cache._cache.get(), {})
            finish.send(sender=None)
            self.assertInactive()

    def test_request_leaves_no_cache(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse("abac_rules")).status_code, 200)
        self.assertInactive()
