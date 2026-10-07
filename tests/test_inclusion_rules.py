import uuid

from django.contrib.auth.models import Group, Permission, User
from django.db import IntegrityError, transaction
from django.test import TestCase

from arches_abac_permissions.models import InclusionRule, InclusionRuleGroupPermission
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)
from arches_abac_permissions.rules.queryset_rule import QuerySetRule
from arches_abac_permissions.rules.search_rule import SearchRule


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


class GetAbacRulesTests(TestCase):
    def setUp(self):
        self.framework = ArchesAbacPermissionFramework()
        self.group = Group.objects.create(name="g")
        self.other_group = Group.objects.create(name="other")
        self.rule = make_rule("mine")
        self.unrelated = make_rule("unrelated")
        InclusionRuleGroupPermission.objects.create(rule=self.rule, group=self.group)
        InclusionRuleGroupPermission.objects.create(
            rule=self.unrelated, group=self.other_group
        )

    def test_none(self):
        self.assertEqual(list(self.framework.get_abac_rules(None)), [])

    def test_group(self):
        self.assertEqual(list(self.framework.get_abac_rules(self.group)), [self.rule])

    def test_user_via_groups_distinct(self):
        user = User.objects.create(username="u")
        user.groups.add(self.group)
        second = Group.objects.create(name="second")
        user.groups.add(second)
        InclusionRuleGroupPermission.objects.create(rule=self.rule, group=second)
        self.assertEqual(list(self.framework.get_abac_rules(user)), [self.rule])

    def test_user_without_groups(self):
        user = User.objects.create(username="lonely")
        self.assertEqual(list(self.framework.get_abac_rules(user)), [])
