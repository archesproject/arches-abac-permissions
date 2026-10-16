import copy

from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import translation

from arches.app.models.models import Node, ResourceInstance, TileModel
from arches_abac_permissions.models import InclusionRuleGroupPermission
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)
from arches_search.models.models import TermSearch

from tests.test_inclusion_rules import LifecycleTestCase, make_rule

FRAMEWORK_LOGGER = (
    "arches_abac_permissions.permissions.arches_abac_permission_framework"
)


def name_query(text, operator="STARTS_WITH", graph_slug="test_graph", alias="name"):
    return {
        "graph_slug": graph_slug,
        "scope": "RESOURCE",
        "logic": "AND",
        "clauses": [
            {
                "type": "LITERAL",
                "quantifier": "ANY",
                "subject": {
                    "type": "NODE",
                    "graph_slug": graph_slug,
                    "node_alias": alias,
                    "search_models": [],
                },
                "operator": operator,
                "operands": [
                    {
                        "type": "LITERAL",
                        "value": {"en": {"value": text, "direction": "ltr"}},
                        "display_value": text,
                    }
                ],
            }
        ],
        "groups": [],
        "aggregations": [],
        "relationship": None,
    }


def resource_field_query(field, operator, value=None):
    return {
        **name_query("x"),
        "clauses": [
            {
                "type": "LITERAL",
                "quantifier": "ANY",
                "subject": {"type": "RESOURCE_FIELD", "field": field},
                "operator": operator,
                "operands": (
                    [] if value is None else [{"type": "LITERAL", "value": value}]
                ),
            }
        ],
    }


def search_models_query(operator, scope="RESOURCE"):
    return {
        **name_query("x"),
        "scope": scope,
        "clauses": [
            {
                "type": "LITERAL",
                "quantifier": "ANY",
                "subject": {
                    "type": "SEARCH_MODELS",
                    "graph_slug": "test_graph",
                    "node_alias": "",
                    "search_models": ["TermSearch"],
                },
                "operator": operator,
                "operands": [],
            }
        ],
    }


class SearchRuleTests(LifecycleTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Node.objects.filter(graph=cls.graph, name="Name").update(alias="name")
        for resource, value in (
            (cls.matching, "Belfast Castle"),
            (cls.also_matching, "Belfast Bunker"),
            (cls.non_matching, "Armagh Abbey"),
        ):
            TermSearch.objects.create(
                tileid=TileModel.objects.get(resourceinstance=resource),
                resourceinstanceid=resource,
                graph_slug="test_graph",
                node_alias="name",
                language="en",
                datatype="string",
                value=value,
            )
        cls.belfast = {cls.matching, cls.also_matching}

    def make_search_rule(self, definition=None):
        if definition is None:
            definition = {"advanced_search_query": name_query("Belfast")}
        return make_rule(
            modulename="search_rule.py", classname="SearchRule", definition=definition
        )

    def grant_view(self, rule):
        group = Group.objects.create(name="Readers")
        user = User.objects.create(username="reader")
        user.groups.add(group)
        grant = InclusionRuleGroupPermission.objects.create(rule=rule, group=group)
        grant.permissions.add(Permission.objects.get(codename="view_resourceinstance"))
        return user

    def test_matching_resources(self):
        rule = self.make_search_rule()
        self.assertEqual(set(rule.get_matching_resources()), self.belfast)
        self.assertTrue(rule.matches_resource(self.matching))
        self.assertFalse(rule.matches_resource(self.non_matching))

    def test_matching_resources_does_not_run_the_search(self):
        rule = self.make_search_rule()
        with CaptureQueriesContext(connection) as queries:
            rule.get_matching_resources()
        self.assertFalse(
            [q for q in queries if "arches_search_terms" in q["sql"]],
            "compiling should only look up the graph and nodes",
        )

    def test_grant_applies_through_filter_resource_queryset(self):
        user = self.grant_view(self.make_search_rule())
        filtered = ArchesAbacPermissionFramework().filter_resource_queryset(
            user, ResourceInstance.objects.filter(graph=self.graph)
        )
        self.assertEqual(set(filtered), self.belfast)

    def test_validation_leaves_the_definition_unchanged(self):
        rule = self.make_search_rule()
        definition = copy.deepcopy(rule.definition)
        rule.clean()
        self.assertEqual(rule.definition, definition)

    def test_invalid_definitions(self):
        cases = {
            "not a dict": [],
            "no query": {},
            "query not a dict": {"advanced_search_query": "monuments"},
            "extra key": {
                "advanced_search_query": name_query("Belfast"),
                "query": {"sql": "SELECT 1"},
            },
            "unknown graph": {
                "advanced_search_query": name_query("x", graph_slug="nope")
            },
            "unknown node": {"advanced_search_query": name_query("x", alias="nope")},
            "unknown operator": {
                "advanced_search_query": name_query("x", operator="BOGUS")
            },
            "no clauses": {"advanced_search_query": {**name_query("x"), "clauses": []}},
            "tile scope with search models": {
                "advanced_search_query": search_models_query(
                    "HAS_ANY_VALUE", scope="TILE"
                )
            },
            "search models with unknown operator": {
                "advanced_search_query": search_models_query("BOGUS")
            },
        }
        for label, definition in cases.items():
            with self.subTest(label):
                rule = self.make_search_rule(definition=definition)
                with self.assertRaises(ValidationError) as cm:
                    rule.clean()
                self.assertIn("definition", cm.exception.message_dict)

    def test_current_user_operators_are_rejected(self):
        for operator in ("IS_CURRENT_USER", "IS_NOT_CURRENT_USER"):
            with self.subTest(operator):
                rule = self.make_search_rule(
                    definition={
                        "advanced_search_query": resource_field_query(
                            "principaluser", operator
                        )
                    }
                )
                with self.assertRaisesMessage(ValidationError, "is not me"):
                    rule.clean()

    def test_matches_the_same_resources_in_every_language(self):
        ResourceInstance.objects.filter(pk=self.matching.pk).update(
            name={"en": "Belfast Castle"}
        )
        rule = self.make_search_rule(
            definition={
                "advanced_search_query": resource_field_query(
                    "name", "STARTS_WITH", "Belfast"
                )
            }
        )
        for language in ("en", "de"):
            with self.subTest(language), translation.override(language):
                self.assertEqual(set(rule.get_matching_resources()), {self.matching})

    def test_rule_broken_after_saving_fails_closed(self):
        user = self.grant_view(self.make_search_rule())
        Node.objects.filter(graph=self.graph, alias="name").update(alias="renamed")
        with self.assertLogs(FRAMEWORK_LOGGER, "ERROR"):
            perms = ArchesAbacPermissionFramework().get_perms(user, self.matching)
        self.assertNotIn("view_resourceinstance", perms)

    def test_search_rule_url_is_false(self):
        self.assertIs(self.make_search_rule().get_search_rule_url(), False)
