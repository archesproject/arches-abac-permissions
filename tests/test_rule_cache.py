from celery.signals import task_postrun, task_prerun
from django.core.signals import request_finished, request_started
from django.core.exceptions import ValidationError
from django.db import connection
from django.urls import reverse
from django.test.utils import CaptureQueriesContext

from arches_abac_permissions import rule_cache
from arches_abac_permissions.rule_cache import rule_definition_cache
from arches_abac_permissions.rules.lifecycle_state_rule import LifecycleStateRule
from arches_abac_permissions.rules.spatial_rule import SpatialRule
from arches_abac_permissions.rules.tile_node_value_rule import TileNodeValueRule
from tests.test_inclusion_rules import make_rule
from tests.test_spatial_rule import SpatialTestCase
from tests.test_tile_node_value_rule import TileNodeValueTestCase
from tests.test_views import ApiTestCase

# Queries left on a cached repeat call: lifecycle has no match query of its own.
LIFECYCLE_MATCH_QUERIES = 0
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


class LifecycleCacheTests(RuleCacheAssertions, TileNodeValueTestCase):
    expected_match_queries = LIFECYCLE_MATCH_QUERIES

    def make_rule_under_test(self):
        return make_rule(
            modulename="lifecycle_state_rule.py",
            classname="LifecycleStateRule",
            definition={
                "graphid": str(self.graph.pk),
                "lifecycle_state_id": str(self.active_state.pk),
            },
        )

    def test_repeat_calls_skip_parsing(self):
        draft = self.make_resource(self.graph, self.draft_state)
        self.assertCacheEffective(self.make_rule_under_test(), self.hit, draft)

    def test_definition_change_is_not_stale(self):
        rule = self.make_rule_under_test()
        with rule_definition_cache():
            self.assertTrue(rule.matches_resource(self.hit))
            rule.definition["lifecycle_state_id"] = str(self.draft_state.pk)
            self.assertFalse(rule.matches_resource(self.hit))

    def test_validation_error_not_cached(self):
        rule = self.make_rule_under_test()
        rule.definition["lifecycle_state_id"] = str(self.other_lifecycle_state.pk)
        with rule_definition_cache():
            for _ in range(2):
                with self.assertRaises(ValidationError):
                    rule.matches_resource(self.hit)
            rule.definition["lifecycle_state_id"] = str(self.active_state.pk)
            self.assertTrue(rule.matches_resource(self.hit))

    def test_get_matching_resources_uses_cache(self):
        rule = self.make_rule_under_test()
        _, uncached = count_queries(lambda: list(rule.get_matching_resources()))
        with rule_definition_cache():
            rule.get_matching_resources()
            matching, cached = count_queries(lambda: set(rule.get_matching_resources()))
        self.assertIn(self.hit, matching)
        self.assertEqual(cached, 1)
        self.assertEqual(uncached, cached + 2)


class SpatialCacheTests(RuleCacheAssertions, SpatialTestCase):
    def setUp(self):
        super().setUp()
        self.hit, self.miss = self.inside, self.outside

    def make_rule_under_test(self):
        return self.make_spatial_rule()

    def test_get_matching_resources_uses_cache(self):
        rule = self.make_rule_under_test()
        _, uncached = count_queries(lambda: list(rule.get_matching_resources()))
        with rule_definition_cache():
            rule.get_matching_resources()
            _, cached = count_queries(lambda: list(rule.get_matching_resources()))
        self.assertLess(cached, uncached)


class TileCacheTests(RuleCacheAssertions, TileNodeValueTestCase):
    def make_rule_under_test(self):
        return self.make_value_rule("string", "hola")

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

    def test_parser_qualnames_differ_per_rule_class(self):
        qualnames = {
            parse.__qualname__
            for parse in (
                LifecycleStateRule.parse_definition,
                SpatialRule.parse_definition,
                TileNodeValueRule.get_tile_filter,
            )
        }
        self.assertEqual(len(qualnames), 3)

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
