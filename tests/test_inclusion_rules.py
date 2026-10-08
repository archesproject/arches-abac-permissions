import uuid

from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from arches.app.models.models import (
    GraphModel,
    Node,
    NodeGroup,
    ResourceInstance,
    TileModel,
)
from arches_abac_permissions.models import InclusionRule, InclusionRuleGroupPermission
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)
from arches_abac_permissions.rules.queryset_rule import QuerySetRule
from arches_abac_permissions.rules.search_rule import SearchRule
from arches_abac_permissions.rules.string_substring_rule import StringSubstringRule


def make_rule(name="rule", **kwargs):
    kwargs.setdefault("definition", {})
    return InclusionRule.objects.create(name=name, **kwargs)


class InclusionRuleTests(TestCase):
    def test_defaults(self):
        rule = make_rule()
        self.assertIsInstance(rule.inclusionruleid, uuid.UUID)
        self.assertIsNotNone(rule.created)
        self.assertIsNone(rule.owner)
        self.assertEqual(InclusionRule._meta.db_table, "inclusion_rules")

    def test_owner_set_null_on_delete(self):
        user = User.objects.create(username="owner")
        rule = make_rule(owner=user)
        user.delete()
        rule.refresh_from_db()
        self.assertIsNone(rule.owner)

    def test_get_class_module(self):
        search = make_rule(
            modulename="search_rule.py", classname="SearchRule", definition={}
        )
        queryset = make_rule(
            modulename="queryset_rule.py", classname="QuerySetRule", definition={}
        )
        self.assertIs(search.get_class_module(), SearchRule)
        self.assertIs(queryset.get_class_module(), QuerySetRule)

    def test_search_rule_url(self):
        rule = make_rule(
            modulename="search_rule.py",
            classname="SearchRule",
            definition={"paging-filter": 1, "term-filter": [{"inverted": False}]},
        )
        url = rule.get_search_rule_url()
        self.assertTrue(url.startswith("/search?"))
        self.assertIn("paging-filter=1", url)
        self.assertIn("term-filter=%5B%7B%22inverted%22%3A%20false%7D%5D", url)

    def test_queryset_rule_url_is_false(self):
        rule = make_rule(modulename="queryset_rule.py", classname="QuerySetRule")
        self.assertIs(rule.get_search_rule_url(), False)


class StringNodeTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.graph = GraphModel.objects.create(name="Test graph", isresource=True)
        cls.nodegroup = NodeGroup.objects.create()
        cls.string_node = cls.make_node("Name", "string")
        cls.number_node = cls.make_node("Count", "number")

        cls.matching = cls.make_resource({"en": "The Getty Villa", "es": "La Villa"})
        cls.other_language = cls.make_resource({"en": "Museum", "es": "Getty Centro"})
        cls.non_matching = cls.make_resource({"en": "Something else"})
        cls.null_value = cls.make_resource(None)
        cls.wildcards = cls.make_resource({"en": "100%_done"})

    @classmethod
    def make_node(cls, name, datatype):
        return Node.objects.create(
            name=name,
            datatype=datatype,
            graph=cls.graph,
            nodegroup=cls.nodegroup,
            istopnode=False,
        )

    @classmethod
    def make_resource(cls, values):
        resource = ResourceInstance.objects.create(graph=cls.graph)
        if values is not None:
            values = {
                language: {"value": value, "direction": "ltr"}
                for language, value in values.items()
            }
        TileModel.objects.create(
            resourceinstance=resource,
            nodegroup=cls.nodegroup,
            data={str(cls.string_node.pk): values},
            sortorder=0,
        )
        return resource

    def make_substring_rule(self, substring, nodeid=None):
        return make_rule(
            modulename="string_substring_rule.py",
            classname="StringSubstringRule",
            definition={
                "nodeid": str(nodeid or self.string_node.pk),
                "substring": substring,
            },
        )


class StringSubstringRuleTests(StringNodeTestCase):
    def matching_resources(self, rule):
        return set(rule.get_class_module().get_matching_resources(rule))

    def test_get_class_module(self):
        rule = self.make_substring_rule("getty")
        self.assertIs(rule.get_class_module(), StringSubstringRule)

    def test_case_insensitive_match_in_any_language(self):
        rule = self.make_substring_rule("gEtTy")
        self.assertEqual(
            self.matching_resources(rule), {self.matching, self.other_language}
        )

    def test_matches_inner_substring(self):
        rule = self.make_substring_rule("villa")
        self.assertEqual(self.matching_resources(rule), {self.matching})

    def test_like_wildcards_are_literal(self):
        self.assertEqual(
            self.matching_resources(self.make_substring_rule("%")), {self.wildcards}
        )
        self.assertEqual(
            self.matching_resources(self.make_substring_rule("0%_d")), {self.wildcards}
        )
        self.assertEqual(
            self.matching_resources(self.make_substring_rule("_")), {self.wildcards}
        )

    def test_matches_resource(self):
        rule = self.make_substring_rule("getty")
        self.assertTrue(StringSubstringRule.matches_resource(rule, self.matching))
        self.assertFalse(
            StringSubstringRule.matches_resource(rule, self.non_matching)
        )
        self.assertFalse(StringSubstringRule.matches_resource(rule, self.null_value))

    def test_search_rule_url_is_false(self):
        self.assertIs(self.make_substring_rule("getty").get_search_rule_url(), False)

    def test_invalid_definitions(self):
        for definition in (
            {},
            {"nodeid": str(self.string_node.pk)},
            {"nodeid": str(self.string_node.pk), "substring": ""},
            {"nodeid": str(self.number_node.pk), "substring": "getty"},
            {"nodeid": str(uuid.uuid4()), "substring": "getty"},
            {"nodeid": "not-a-uuid", "substring": "getty"},
        ):
            with self.subTest(definition=definition):
                rule = make_rule(
                    modulename="string_substring_rule.py",
                    classname="StringSubstringRule",
                    definition=definition,
                )
                with self.assertRaises(ValidationError):
                    StringSubstringRule.get_matching_resources(rule)


class InclusionRuleGroupPermissionTests(TestCase):
    def setUp(self):
        self.rule = make_rule()
        self.group = Group.objects.create(name="g")

    def test_unique_rule_group(self):
        InclusionRuleGroupPermission.objects.create(rule=self.rule, group=self.group)
        with self.assertRaises(IntegrityError), transaction.atomic():
            InclusionRuleGroupPermission.objects.create(
                rule=self.rule, group=self.group
            )

    def test_permissions_m2m(self):
        perm = Permission.objects.get(codename="view_resourceinstance")
        grant = InclusionRuleGroupPermission.objects.create(
            rule=self.rule, group=self.group
        )
        grant.permissions.add(perm)
        self.assertEqual(list(grant.permissions.all()), [perm])
        self.assertEqual(list(self.rule.group_permissions.all()), [grant])


class AbacRuleEvaluationTests(StringNodeTestCase):
    def setUp(self):
        self.framework = ArchesAbacPermissionFramework()
        self.group = Group.objects.create(name="Getty readers")
        self.user = User.objects.create(username="reader")
        self.user.groups.add(self.group)
        self.user.user_permissions.add(
            Permission.objects.get(codename="read_nodegroup")
        )
        self.grant(self.make_substring_rule("getty"), "view_resourceinstance")

    def grant(self, rule, *codenames, group=None):
        grant = InclusionRuleGroupPermission.objects.create(
            rule=rule, group=group or self.group
        )
        grant.permissions.set(Permission.objects.filter(codename__in=codenames))

    def test_get_perms_includes_rule_perms_for_matching_resource(self):
        self.assertIn(
            "view_resourceinstance", self.framework.get_perms(self.group, self.matching)
        )
        self.assertIn(
            "view_resourceinstance", self.framework.get_perms(self.user, self.matching)
        )

    def test_get_perms_excludes_rule_perms_for_non_matching_resource(self):
        self.assertNotIn(
            "view_resourceinstance",
            self.framework.get_perms(self.user, self.non_matching),
        )

    def test_only_granted_perms_are_added(self):
        self.assertNotIn(
            "change_resourceinstance",
            self.framework.get_perms(self.user, self.matching),
        )

    def test_rules_of_other_groups_do_not_apply(self):
        other_group = Group.objects.create(name="Villa editors")
        self.grant(
            self.make_substring_rule("villa"),
            "change_resourceinstance",
            group=other_group,
        )
        self.assertNotIn(
            "change_resourceinstance",
            self.framework.get_perms(self.user, self.matching),
        )

    def test_has_group_perm(self):
        self.assertTrue(
            self.framework.has_group_perm(
                self.group, "view_resourceinstance", self.matching
            )
        )
        self.assertFalse(
            self.framework.has_group_perm(
                self.group, "view_resourceinstance", self.non_matching
            )
        )

    def test_user_can_read_resource(self):
        self.assertTrue(
            self.framework.user_can_read_resource(self.user, resource=self.matching)
        )
        self.assertFalse(
            self.framework.user_can_read_resource(self.user, resource=self.non_matching)
        )
        self.assertFalse(
            self.framework.user_can_edit_resource(self.user, resource=self.matching)
        )

    def test_filter_resource_queryset_includes_rule_matches(self):
        filtered = self.framework.filter_resource_queryset(
            self.user, ResourceInstance.objects.filter(graph=self.graph)
        )
        self.assertEqual(set(filtered), {self.matching, self.other_language})

    def test_filter_resource_queryset_by_other_field(self):
        filtered = self.framework.filter_resource_queryset(
            self.user,
            TileModel.objects.filter(nodegroup=self.nodegroup),
            resourceinstance_field="resourceinstance_id",
        )
        self.assertEqual(
            {tile.resourceinstance_id for tile in filtered},
            {self.matching.pk, self.other_language.pk},
        )

    def test_filter_resource_queryset_only_granted_permission(self):
        filtered = self.framework.filter_resource_queryset(
            self.user,
            ResourceInstance.objects.filter(graph=self.graph),
            permission="models.change_resourceinstance",
        )
        self.assertFalse(filtered.exists())

    def test_filter_resource_queryset_keeps_explicit_grants(self):
        self.framework.assign_perm(
            "view_resourceinstance", self.group, self.non_matching
        )
        filtered = self.framework.filter_resource_queryset(
            self.user, ResourceInstance.objects.filter(graph=self.graph)
        )
        self.assertEqual(
            set(filtered), {self.matching, self.other_language, self.non_matching}
        )

    def test_filter_resource_queryset_ignores_unevaluated_rules(self):
        self.grant(
            make_rule(modulename="search_rule.py", classname="SearchRule"),
            "view_resourceinstance",
        )
        filtered = self.framework.filter_resource_queryset(
            self.user, ResourceInstance.objects.filter(graph=self.graph)
        )
        self.assertEqual(set(filtered), {self.matching, self.other_language})
