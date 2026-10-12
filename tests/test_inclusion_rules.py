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
    ResourceInstanceLifecycle,
    ResourceInstanceLifecycleState,
    TileModel,
)
from arches_abac_permissions.models import InclusionRule, InclusionRuleGroupPermission
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)
from arches_abac_permissions.rules.lifecycle_state_rule import LifecycleStateRule
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


class LifecycleTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        lifecycle = ResourceInstanceLifecycle.objects.create(name="Test lifecycle")
        cls.draft_state = cls.make_state(lifecycle, "Draft", is_initial_state=True)
        cls.active_state = cls.make_state(lifecycle, "Active")
        other_lifecycle = ResourceInstanceLifecycle.objects.create(name="Other")
        cls.other_lifecycle_state = cls.make_state(
            other_lifecycle, "Other initial", is_initial_state=True
        )

        cls.graph = cls.make_graph("test_graph", lifecycle)
        cls.other_graph = cls.make_graph("other_graph", lifecycle)
        cls.branch = GraphModel.objects.create(
            name="Branch", slug="branch", isresource=False
        )
        cls.nodegroup = NodeGroup.objects.create()
        # Reading a resource requires read_nodegroup on a node of its graph.
        Node.objects.create(
            name="Name",
            datatype="string",
            graph=cls.graph,
            nodegroup=cls.nodegroup,
            istopnode=False,
        )

        cls.matching = cls.make_resource(cls.graph, cls.active_state)
        cls.also_matching = cls.make_resource(cls.graph, cls.active_state)
        cls.non_matching = cls.make_resource(cls.graph, cls.draft_state)
        cls.other_graph_active = cls.make_resource(cls.other_graph, cls.active_state)

    @staticmethod
    def make_state(lifecycle, name, is_initial_state=False):
        return ResourceInstanceLifecycleState.objects.create(
            name=name,
            action_label=name,
            resource_instance_lifecycle=lifecycle,
            is_initial_state=is_initial_state,
        )

    @staticmethod
    def make_graph(slug, lifecycle):
        return GraphModel.objects.create(
            name=slug,
            slug=slug,
            isresource=True,
            resource_instance_lifecycle=lifecycle,
        )

    @classmethod
    def make_resource(cls, graph, state):
        resource = ResourceInstance.objects.create(
            graph=graph, resource_instance_lifecycle_state=state
        )
        TileModel.objects.create(
            resourceinstance=resource, nodegroup=cls.nodegroup, data={}, sortorder=0
        )
        return resource

    def make_lifecycle_rule(self, state=None, graph=None):
        return make_rule(
            modulename="lifecycle_state_rule.py",
            classname="LifecycleStateRule",
            definition={
                "graphid": str((graph or self.graph).pk),
                "lifecycle_state_id": str((state or self.active_state).pk),
            },
        )


class LifecycleStateRuleTests(LifecycleTestCase):
    def matching_resources(self, rule):
        return set(rule.get_class_module().get_matching_resources(rule))

    def test_get_class_module(self):
        rule = self.make_lifecycle_rule()
        self.assertIs(rule.get_class_module(), LifecycleStateRule)

    def test_matches_graph_and_state(self):
        self.assertEqual(
            self.matching_resources(self.make_lifecycle_rule()),
            {self.matching, self.also_matching},
        )
        self.assertEqual(
            self.matching_resources(self.make_lifecycle_rule(self.draft_state)),
            {self.non_matching},
        )
        self.assertEqual(
            self.matching_resources(self.make_lifecycle_rule(graph=self.other_graph)),
            {self.other_graph_active},
        )

    def test_matches_resource(self):
        rule = self.make_lifecycle_rule()
        self.assertTrue(LifecycleStateRule.matches_resource(rule, self.matching))
        self.assertFalse(LifecycleStateRule.matches_resource(rule, self.non_matching))
        self.assertFalse(
            LifecycleStateRule.matches_resource(rule, self.other_graph_active)
        )

    def test_search_rule_url(self):
        url = self.make_lifecycle_rule().get_search_rule_url()
        self.assertTrue(url.startswith("/search?"))
        self.assertIn(f"%22graphid%22%3A%20%22{self.graph.pk}%22", url)
        self.assertIn(f"%22id%22%3A%20%22{self.active_state.pk}%22", url)

    def test_invalid_definitions(self):
        graphid = str(self.graph.pk)
        stateid = str(self.active_state.pk)
        for definition in (
            {},
            {"graphid": graphid},
            {"lifecycle_state_id": stateid},
            {"graphid": str(uuid.uuid4()), "lifecycle_state_id": stateid},
            {"graphid": "not-a-uuid", "lifecycle_state_id": stateid},
            {"graphid": str(self.branch.pk), "lifecycle_state_id": stateid},
            {"graphid": graphid, "lifecycle_state_id": str(uuid.uuid4())},
            {"graphid": graphid, "lifecycle_state_id": "not-a-uuid"},
            {
                "graphid": graphid,
                "lifecycle_state_id": str(self.other_lifecycle_state.pk),
            },
        ):
            with self.subTest(definition=definition):
                rule = make_rule(
                    modulename="lifecycle_state_rule.py",
                    classname="LifecycleStateRule",
                    definition=definition,
                )
                with self.assertRaises(ValidationError):
                    LifecycleStateRule.get_matching_resources(rule)


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


class AbacRuleEvaluationTests(LifecycleTestCase):
    def setUp(self):
        self.framework = ArchesAbacPermissionFramework()
        self.group = Group.objects.create(name="Active readers")
        self.user = User.objects.create(username="reader")
        self.user.groups.add(self.group)
        self.user.user_permissions.add(
            Permission.objects.get(codename="read_nodegroup")
        )
        self.grant(self.make_lifecycle_rule(), "view_resourceinstance")

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
        other_group = Group.objects.create(name="Active editors")
        self.grant(
            self.make_lifecycle_rule(),
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
        self.assertEqual(set(filtered), {self.matching, self.also_matching})

    def test_filter_resource_queryset_by_other_field(self):
        filtered = self.framework.filter_resource_queryset(
            self.user,
            TileModel.objects.filter(nodegroup=self.nodegroup),
            resourceinstance_field="resourceinstance_id",
        )
        self.assertEqual(
            {tile.resourceinstance_id for tile in filtered},
            {self.matching.pk, self.also_matching.pk},
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
            set(filtered), {self.matching, self.also_matching, self.non_matching}
        )

    def test_filter_resource_queryset_ignores_unevaluated_rules(self):
        self.grant(
            make_rule(modulename="search_rule.py", classname="SearchRule"),
            "view_resourceinstance",
        )
        filtered = self.framework.filter_resource_queryset(
            self.user, ResourceInstance.objects.filter(graph=self.graph)
        )
        self.assertEqual(set(filtered), {self.matching, self.also_matching})
