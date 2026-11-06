import uuid
from unittest import mock

from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.core.signals import request_finished, request_started
from django.db import DatabaseError, IntegrityError, transaction
from django.db.utils import ProgrammingError
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
    end_request_reporting,
    start_request_reporting,
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

    def test_inactive_rules_grant_nothing(self):
        InclusionRule.objects.update(active=False)
        self.assertNotIn(
            "view_resourceinstance", self.framework.get_perms(self.user, self.matching)
        )
        self.assertFalse(
            self.framework.get_abac_resources(
                self.user, "models.view_resourceinstance"
            ).exists()
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

    # A rule that cannot be evaluated matches nothing and breaks nothing.
    framework_logger = (
        "arches_abac_permissions.permissions.arches_abac_permission_framework"
    )

    def broken_rules(self):
        return [
            make_rule(modulename="lifecycle_state_rule.py", classname="Missing"),
            make_rule(
                modulename="lifecycle_state_rule.py",
                classname="LifecycleStateRule",
                definition={},
            ),
        ]

    def test_get_perms_ignores_broken_rule(self):
        for rule in self.broken_rules():
            with self.subTest(rule=rule.classname):
                self.grant(rule, "change_resourceinstance")
                with self.assertLogs(self.framework_logger, "ERROR"):
                    perms = self.framework.get_perms(self.user, self.matching)
                self.assertIn("view_resourceinstance", perms)
                self.assertNotIn("change_resourceinstance", perms)

    def test_filter_resource_queryset_ignores_broken_rule(self):
        for rule in self.broken_rules():
            with self.subTest(rule=rule.classname):
                self.grant(rule, "view_resourceinstance")
                with self.assertLogs(self.framework_logger, "ERROR"):
                    filtered = self.framework.filter_resource_queryset(
                        self.user, ResourceInstance.objects.filter(graph=self.graph)
                    )
                self.assertEqual(set(filtered), {self.matching, self.also_matching})


class DatabaseErrorTests(LifecycleTestCase):
    setUp = AbacRuleEvaluationTests.setUp
    grant = AbacRuleEvaluationTests.grant
    framework_logger = AbacRuleEvaluationTests.framework_logger

    def test_database_errors_propagate_from_matches_resource(self):
        for error in (DatabaseError, ProgrammingError):
            with self.subTest(error=error.__name__):
                with mock.patch.object(
                    LifecycleStateRule, "matches_resource", side_effect=error("boom")
                ):
                    with self.assertNoLogs(self.framework_logger, "ERROR"):
                        with self.assertRaises(DatabaseError):
                            self.framework.get_perms(self.user, self.matching)

    def test_database_errors_propagate_from_get_matching_resources(self):
        for error in (DatabaseError, ProgrammingError):
            with self.subTest(error=error.__name__):
                with mock.patch.object(
                    LifecycleStateRule,
                    "get_matching_resources",
                    side_effect=error("boom"),
                ):
                    with self.assertNoLogs(self.framework_logger, "ERROR"):
                        with self.assertRaises(DatabaseError):
                            self.framework.get_abac_resources(
                                self.user, "view_resourceinstance"
                            )
                        with self.assertRaises(DatabaseError):
                            self.framework.filter_resource_queryset(
                                self.user,
                                ResourceInstance.objects.filter(graph=self.graph),
                            )


class RuleErrorLoggingTests(LifecycleTestCase):
    setUp = AbacRuleEvaluationTests.setUp
    grant = AbacRuleEvaluationTests.grant
    framework_logger = AbacRuleEvaluationTests.framework_logger

    def setUp(self):
        AbacRuleEvaluationTests.setUp(self)
        self.grant(self.make_lifecycle_rule(), "view_resourceinstance")

    # The signal receivers also close DB connections, so call the handlers.
    def start_request(self):
        start_request_reporting()
        self.addCleanup(end_request_reporting)

    def test_handlers_are_connected_to_request_signals(self):
        for signal, uid in (
            (request_started, "abac_start_request_reporting"),
            (request_finished, "abac_end_request_reporting"),
        ):
            self.assertTrue(any(key[0] == uid for key, *_ in signal.receivers))

    def evaluate_one_rule(self, rule):
        with mock.patch.object(
            LifecycleStateRule, "matches_resource", side_effect=ValueError("bad")
        ):
            with self.assertLogs(self.framework_logger, "DEBUG") as logs:
                self.framework.evaluate_rule(
                    rule, lambda r: r.matches_resource(self.matching), default=False
                )
        return [record.levelname for record in logs.records]

    def test_logs_once_per_rule_per_request(self):
        rule = InclusionRule.objects.first()
        self.start_request()
        self.assertEqual(self.evaluate_one_rule(rule), ["ERROR"])
        self.assertEqual(self.evaluate_one_rule(rule), ["DEBUG"])

    def test_each_failing_rule_logs_once(self):
        first, second = InclusionRule.objects.order_by("pk")[:2]
        self.start_request()
        self.assertEqual(self.evaluate_one_rule(first), ["ERROR"])
        self.assertEqual(self.evaluate_one_rule(second), ["ERROR"])
        self.assertEqual(self.evaluate_one_rule(first), ["DEBUG"])

    def test_logs_again_in_next_request(self):
        rule = InclusionRule.objects.first()
        self.start_request()
        self.assertEqual(self.evaluate_one_rule(rule), ["ERROR"])
        end_request_reporting()
        start_request_reporting()
        self.assertEqual(self.evaluate_one_rule(rule), ["ERROR"])

    def test_logs_every_time_outside_a_request(self):
        rule = InclusionRule.objects.first()
        self.assertEqual(self.evaluate_one_rule(rule), ["ERROR"])
        self.assertEqual(self.evaluate_one_rule(rule), ["ERROR"])


class LifecycleStateRuleTranslationTests(LifecycleTestCase):
    def test_validation_messages_are_translated(self):
        bad_id = str(uuid.uuid4())
        cases = [
            ({}, []),
            ({"graphid": bad_id, "lifecycle_state_id": bad_id}, [bad_id]),
            (
                {
                    "graphid": str(self.graph.pk),
                    "lifecycle_state_id": bad_id,
                },
                [bad_id, str(self.graph.pk)],
            ),
        ]
        with mock.patch(
            "arches_abac_permissions.rules.lifecycle_state_rule._",
            lambda message: "T:" + message,
        ):
            for definition, ids in cases:
                with self.subTest(definition=definition):
                    with self.assertRaises(ValidationError) as cm:
                        LifecycleStateRule.parse_definition(definition)
                    message = cm.exception.messages[0]
                    self.assertTrue(message.startswith("T:"))
                    for value in ids:
                        self.assertIn(value, message)

    def test_validation_message_text(self):
        bad_id = str(uuid.uuid4())
        with self.assertRaisesMessage(
            ValidationError, f"{bad_id} is not the id of a resource model."
        ):
            LifecycleStateRule.parse_definition(
                {"graphid": bad_id, "lifecycle_state_id": bad_id}
            )


class InclusionRuleValidationTests(LifecycleTestCase):
    def assertInvalid(self, rule, field):
        with self.assertRaises(ValidationError) as cm:
            rule.clean()
        if field:
            self.assertIn(field, cm.exception.message_dict)

    def test_valid_rule(self):
        self.make_lifecycle_rule().clean()

    def test_rule_class_without_definition_checks(self):
        make_rule(modulename="search_rule.py", classname="SearchRule").clean()

    def test_missing_rule_class(self):
        self.assertInvalid(make_rule(), None)
        self.assertInvalid(make_rule(modulename="search_rule.py"), None)

    def test_unknown_rule_class(self):
        self.assertInvalid(
            make_rule(modulename="lifecycle_state_rule.py", classname="Missing"),
            "classname",
        )
        self.assertInvalid(
            make_rule(modulename="missing_rule.py", classname="MissingRule"),
            "classname",
        )

    def test_name_in_module_that_is_not_a_rule_class(self):
        for classname in ("GraphModel", "urlencode", "json"):
            with self.subTest(classname=classname):
                self.assertInvalid(
                    make_rule(
                        modulename="lifecycle_state_rule.py", classname=classname
                    ),
                    "classname",
                )

    def test_definition_not_an_object(self):
        for definition in ([], "x", 1):
            with self.subTest(definition=definition):
                self.assertInvalid(
                    make_rule(
                        modulename="lifecycle_state_rule.py",
                        classname="LifecycleStateRule",
                        definition=definition,
                    ),
                    "definition",
                )

    def test_invalid_definition(self):
        rule = make_rule(
            modulename="lifecycle_state_rule.py",
            classname="LifecycleStateRule",
            definition={"graphid": str(self.graph.pk)},
        )
        self.assertInvalid(rule, "definition")
