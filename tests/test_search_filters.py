import json
from unittest import mock

from django.contrib.auth.models import Group, Permission, User

from arches.app.search.elasticsearch_dsl_builder import Bool, Term
from arches_abac_permissions.models import InclusionRuleGroupPermission
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)
from arches_abac_permissions.rules.lifecycle_state_rule import LifecycleStateRule
from tests.test_inclusion_rules import LifecycleTestCase, make_rule

FRAMEWORK_LOGGER = (
    "arches_abac_permissions.permissions.arches_abac_permission_framework"
)


def dsl(search_filter):
    return json.loads(json.dumps(search_filter.dsl))


def lifecycle_filter(inclusion_rule):
    """Stands in for a rule's Elasticsearch filter."""
    state = inclusion_rule.definition["lifecycle_state_id"]
    return Term(field="resource_instance_lifecycle_state_id", term=state)


class PermissionSearchFilterTests(LifecycleTestCase):
    def setUp(self):
        self.framework = ArchesAbacPermissionFramework()
        self.group = Group.objects.create(name="searchers")
        self.user = User.objects.create(username="searcher")
        self.user.groups.add(self.group)
        patch = mock.patch.object(
            LifecycleStateRule, "get_search_filter", side_effect=lifecycle_filter
        )
        patch.start()
        self.addCleanup(patch.stop)

    def grant(self, rule, codename="view_resourceinstance"):
        grant = InclusionRuleGroupPermission.objects.create(rule=rule, group=self.group)
        grant.permissions.set(Permission.objects.filter(codename=codename))

    def rule_clauses(self):
        should = dsl(self.framework.get_permission_search_filter(self.user))["bool"][
            "filter"
        ][0]["bool"]["should"]
        # The first clause is the default-deny filter.
        return should[1:]

    def test_rules_without_a_filter_have_none(self):
        rule = make_rule(
            modulename="tile_node_value_rule.py",
            classname="TileNodeValueRule",
            definition={},
        )
        self.assertIsNone(rule.get_search_filter_for_rule())

    def test_adds_filters_of_rules_granting_read(self):
        active = self.make_lifecycle_rule()
        self.grant(active)
        self.assertEqual(
            self.rule_clauses(), [dsl(active.get_search_filter_for_rule())]
        )

    def test_ignores_other_grants_and_rules(self):
        self.grant(self.make_lifecycle_rule(), codename="change_resourceinstance")
        inactive = self.make_lifecycle_rule(state=self.draft_state)
        inactive.active = False
        inactive.save()
        self.grant(inactive)
        self.grant(
            make_rule(
                modulename="tile_node_value_rule.py", classname="TileNodeValueRule"
            )
        )
        other_group = Group.objects.create(name="others")
        InclusionRuleGroupPermission.objects.create(
            rule=self.make_lifecycle_rule(), group=other_group
        ).permissions.set(Permission.objects.filter(codename="view_resourceinstance"))
        self.assertEqual(self.rule_clauses(), [])

    def test_skips_an_empty_filter(self):
        self.grant(self.make_lifecycle_rule())
        with mock.patch.object(
            LifecycleStateRule, "get_search_filter", return_value=Bool()
        ):
            self.assertEqual(self.rule_clauses(), [])

    def test_skips_a_broken_rule(self):
        broken = self.make_lifecycle_rule()
        broken.definition = {}
        broken.save()
        self.grant(broken)
        with self.assertLogs(FRAMEWORK_LOGGER):
            self.assertEqual(self.rule_clauses(), [])
