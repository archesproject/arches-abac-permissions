import uuid
from unittest import mock, skipUnless

from django.apps import apps
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError

from arches.app.models.models import ResourceInstance
from arches_abac_permissions.models import InclusionRuleGroupPermission
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)
from arches_abac_permissions.rules.resource_set_rule import ResourceSetRule
from tests.test_inclusion_rules import LifecycleTestCase, make_rule

FRAMEWORK_LOGGER = (
    "arches_abac_permissions.permissions.arches_abac_permission_framework"
)
RESOURCE_SETS_INSTALLED = apps.is_installed("arches_resource_sets")
if RESOURCE_SETS_INSTALLED:
    from arches_resource_sets.models import ResourceSet


def make_set_rule(definition):
    return make_rule(
        modulename="resource_set_rule.py",
        classname="ResourceSetRule",
        definition=definition,
    )


class ResourceSetRuleDefinitionTests(LifecycleTestCase):
    def test_get_class_module(self):
        rule = make_set_rule({"resource_set_id": str(uuid.uuid4())})
        self.assertIs(rule.get_class_module(), ResourceSetRule)

    @mock.patch(
        "arches_abac_permissions.rules.resource_set_rule.RESOURCE_SETS_INSTALLED",
        False,
    )
    def test_without_arches_resource_sets(self):
        rule = make_set_rule({"resource_set_id": str(uuid.uuid4())})
        with self.assertRaises(ValidationError):
            rule.clean()
        with self.assertRaises(ValidationError):
            rule.matches_resource(self.matching)
        with self.assertRaises(ValidationError):
            rule.get_matching_resources()


@skipUnless(RESOURCE_SETS_INSTALLED, "arches-resource-sets is not installed")
class ResourceSetRuleTests(LifecycleTestCase):
    def setUp(self):
        self.owner = User.objects.create(username="set owner")
        self.resource_set = ResourceSet.objects.create(owner=self.owner)
        self.resource_set.add_members([self.matching.pk, self.other_graph_active.pk])
        self.rule = make_set_rule({"resource_set_id": str(self.resource_set.pk)})

    def test_matches_set_members(self):
        self.assertEqual(
            set(self.rule.get_matching_resources()),
            {self.matching, self.other_graph_active},
        )
        self.assertTrue(self.rule.matches_resource(self.matching))
        self.assertFalse(self.rule.matches_resource(self.non_matching))

    def test_membership_changes_apply_without_touching_the_rule(self):
        self.resource_set.remove_members([self.matching.pk])
        self.resource_set.add_members([self.non_matching.pk])
        self.assertFalse(self.rule.matches_resource(self.matching))
        self.assertTrue(self.rule.matches_resource(self.non_matching))

    def test_deleted_set_matches_nothing(self):
        self.resource_set.delete()
        self.assertFalse(self.rule.get_matching_resources().exists())
        self.assertFalse(self.rule.matches_resource(self.matching))

    def test_search_rule_url_is_false(self):
        self.assertIs(self.rule.get_search_rule_url(), False)

    def test_valid_definition(self):
        self.rule.clean()

    def test_missing_set_id(self):
        for definition in ({}, {"resource_set_id": ""}):
            with self.subTest(definition=definition):
                with self.assertRaises(ValidationError) as cm:
                    make_set_rule(definition).clean()
                self.assertEqual(
                    cm.exception.message_dict["definition"],
                    ["Resource set rules require a 'resource_set_id'."],
                )

    def test_unknown_set(self):
        for set_id in (str(uuid.uuid4()), "not-a-uuid"):
            with self.subTest(set_id=set_id):
                with self.assertRaises(ValidationError) as cm:
                    make_set_rule({"resource_set_id": set_id}).clean()
                self.assertIn("definition", cm.exception.message_dict)

    def test_grants_access_to_set_members(self):
        framework = ArchesAbacPermissionFramework()
        group = Group.objects.create(name="Set readers")
        user = User.objects.create(username="set reader")
        user.groups.add(group)
        user.user_permissions.add(Permission.objects.get(codename="read_nodegroup"))
        grant = InclusionRuleGroupPermission.objects.create(rule=self.rule, group=group)
        grant.permissions.add(Permission.objects.get(codename="view_resourceinstance"))

        self.assertTrue(framework.user_can_read_resource(user, resource=self.matching))
        self.assertFalse(
            framework.user_can_read_resource(user, resource=self.non_matching)
        )
        filtered = framework.filter_resource_queryset(
            user, ResourceInstance.objects.filter(graph=self.graph)
        )
        self.assertEqual(set(filtered), {self.matching})

    def test_rule_that_cannot_be_evaluated_grants_nothing(self):
        framework = ArchesAbacPermissionFramework()
        group = Group.objects.create(name="Broken set readers")
        user = User.objects.create(username="broken set reader")
        user.groups.add(group)
        user.user_permissions.add(Permission.objects.get(codename="read_nodegroup"))
        grant = InclusionRuleGroupPermission.objects.create(
            rule=make_set_rule({"resource_set_id": "not-a-uuid"}), group=group
        )
        grant.permissions.add(Permission.objects.get(codename="view_resourceinstance"))

        with self.assertLogs(FRAMEWORK_LOGGER, "ERROR"):
            self.assertFalse(
                framework.user_can_read_resource(user, resource=self.matching)
            )
        with self.assertLogs(FRAMEWORK_LOGGER, "ERROR"):
            filtered = framework.filter_resource_queryset(
                user, ResourceInstance.objects.filter(graph=self.graph)
            )
        self.assertFalse(filtered.exists())
