import copy
import json
from unittest import mock, skipUnless

from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation

from arches.app.models.models import Node, ResourceInstance, TileModel
from arches_abac_permissions.models import InclusionRule, InclusionRuleGroupPermission
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)
from arches_abac_permissions.rules.search_rule import SearchRule
from tests.test_inclusion_rules import LifecycleTestCase, make_rule

ARCHES_SEARCH_INSTALLED = SearchRule.rule_type.available
if ARCHES_SEARCH_INSTALLED:
    from arches_search.models.models import TermSearch

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


def with_operand_value(query, value):
    query["clauses"][0]["operands"][0]["value"] = value
    return query


def unclosed_area_query():
    unclosed_ring = [[[0, 0], [1, 1]]]
    return {
        **name_query("x"),
        "clauses": [
            {
                "type": "LITERAL",
                "quantifier": "ANY",
                "subject": {
                    "type": "SEARCH_MODELS",
                    "graph_slug": "test_graph",
                    "node_alias": "",
                    "search_models": ["GeometrySearch"],
                },
                "operator": "GEO_INTERSECTS",
                "operands": [
                    {
                        "type": "GEO_LITERAL",
                        "value": {
                            "type": "FeatureCollection",
                            "features": [
                                {
                                    "type": "Feature",
                                    "properties": {},
                                    "geometry": {
                                        "type": "Polygon",
                                        "coordinates": unclosed_ring,
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


class SearchRuleDefinitionTests(LifecycleTestCase):
    @mock.patch(
        "arches_abac_permissions.rules.search_rule.ARCHES_SEARCH_INSTALLED", False
    )
    def test_without_arches_search(self):
        rule = make_rule(
            modulename="search_rule.py",
            classname="SearchRule",
            definition={"advanced_search_query": name_query("Belfast")},
        )
        with self.assertRaises(ValidationError):
            rule.clean()
        with self.assertRaises(ValidationError):
            rule.matches_resource(self.matching)
        with self.assertRaises(ValidationError):
            rule.get_matching_resources()


@skipUnless(ARCHES_SEARCH_INSTALLED, "arches-search is not installed")
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
            "clauses only in aggregations": {
                "advanced_search_query": {
                    **name_query("x"),
                    "clauses": [],
                    "aggregations": [{"clauses": [1]}],
                }
            },
            "clauses only under an unknown key": {
                "advanced_search_query": {
                    **name_query("x"),
                    "clauses": [],
                    "note": {"clauses": [1]},
                }
            },
            "tile scope with search models": {
                "advanced_search_query": search_models_query(
                    "HAS_ANY_VALUE", scope="TILE"
                )
            },
            "search models with unknown operator": {
                "advanced_search_query": search_models_query("BOGUS")
            },
            "operand that fails when run": {
                "advanced_search_query": with_operand_value(
                    name_query("x", operator="EQUALS"), [1, 2]
                )
            },
            "unclosed area": {"advanced_search_query": unclosed_area_query()},
            "empty value": {"advanced_search_query": name_query("")},
            "blank value": {"advanced_search_query": name_query("  ")},
        }
        for label, definition in cases.items():
            with self.subTest(label):
                rule = self.make_search_rule(definition=definition)
                with self.assertRaises(ValidationError) as cm:
                    rule.clean()
                self.assertIn("definition", cm.exception.message_dict)

    def test_clauses_in_nested_groups_count(self):
        query = {**name_query("x"), "clauses": [], "groups": [name_query("Belfast")]}
        rule = self.make_search_rule({"advanced_search_query": query})
        rule.clean()
        self.assertEqual(set(rule.get_matching_resources()), self.belfast)

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

    def post_rule(self, definition):
        self.client.force_login(User.objects.create_superuser("api_admin"))
        return self.client.post(
            reverse("abac_rules"),
            data=json.dumps(
                {"name": "Belfast", "rule_type": "search", "definition": definition}
            ),
            content_type="application/json",
        )

    def test_created_through_the_rules_api(self):
        query = name_query("Belfast")
        response = self.post_rule({"advanced_search_query": query})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(
            response.json()["definition"], {"advanced_search_query": query}
        )
        rule = InclusionRule.objects.get(pk=response.json()["id"])
        self.assertEqual(set(rule.get_matching_resources()), self.belfast)

    def test_rules_api_rejects_a_query_that_cannot_run(self):
        response = self.post_rule({"advanced_search_query": unclosed_area_query()})
        self.assertEqual(response.status_code, 400)
        self.assertIn("The query can't be run", response.json()["message"])
