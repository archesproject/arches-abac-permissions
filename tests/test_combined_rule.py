import uuid
from unittest import mock

from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError

from arches.app.models.models import ResourceInstance
from arches.app.search.elasticsearch_dsl_builder import Bool
from arches_abac_permissions.models import InclusionRuleGroupPermission
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)
from arches_abac_permissions.rules.combined_rule import CombinedRule
from arches_abac_permissions.rules.lifecycle_state_rule import LifecycleStateRule
from tests.test_inclusion_rules import LifecycleTestCase, make_rule
from tests.test_search_filters import dsl


def make_combined_rule(operator, rule_ids, exclude_rule_ids=(), name="combined"):
    return make_rule(
        name=name,
        modulename="combined_rule.py",
        classname="CombinedRule",
        definition={
            "operator": operator,
            "rule_ids": [str(pk) for pk in rule_ids],
            "exclude_rule_ids": [str(pk) for pk in exclude_rule_ids],
        },
    )


class CombinedRuleTests(LifecycleTestCase):
    def setUp(self):
        self.active_rule = self.make_lifecycle_rule()
        self.other_active_rule = self.make_lifecycle_rule(graph=self.other_graph)
        self.draft_rule = self.make_lifecycle_rule(state=self.draft_state)

    def assertMatches(self, rule, expected):
        self.assertEqual(set(rule.get_matching_resources()), set(expected))
        for resource in (
            self.matching,
            self.also_matching,
            self.non_matching,
            self.other_graph_active,
        ):
            self.assertEqual(rule.matches_resource(resource), resource in expected)

    def test_get_class_module(self):
        rule = make_combined_rule("or", [self.active_rule.pk])
        self.assertIs(rule.get_class_module(), CombinedRule)

    def test_or(self):
        rule = make_combined_rule("or", [self.active_rule.pk, self.draft_rule.pk])
        self.assertMatches(rule, {self.matching, self.also_matching, self.non_matching})

    def test_and(self):
        either = make_combined_rule(
            "or", [self.active_rule.pk, self.other_active_rule.pk]
        )
        rule = make_combined_rule("and", [either.pk, self.active_rule.pk])
        self.assertMatches(rule, {self.matching, self.also_matching})

    def test_and_with_disjoint_rules_matches_nothing(self):
        rule = make_combined_rule("and", [self.active_rule.pk, self.draft_rule.pk])
        self.assertMatches(rule, set())

    def test_exclude(self):
        both = make_combined_rule(
            "or", [self.active_rule.pk, self.other_active_rule.pk]
        )
        rule = make_combined_rule("or", [both.pk], [self.other_active_rule.pk])
        self.assertMatches(rule, {self.matching, self.also_matching})

    def test_nested_groups(self):
        # Draft records, or active ones except the other model's.
        rule = make_combined_rule("or", [self.draft_rule.pk])
        rule.definition["groups"] = [
            {
                "operator": "or",
                "rule_ids": [str(self.active_rule.pk), str(self.other_active_rule.pk)],
                "exclude_rule_ids": [str(self.other_active_rule.pk)],
            }
        ]
        rule.save()
        self.assertMatches(rule, {self.matching, self.also_matching, self.non_matching})

    def test_group_of_groups_without_rules(self):
        rule = make_combined_rule("and", [self.active_rule.pk])
        rule.definition = {
            "operator": "and",
            "groups": [
                {"operator": "or", "rule_ids": [str(self.active_rule.pk)]},
                {
                    "operator": "or",
                    "rule_ids": [
                        str(self.active_rule.pk),
                        str(self.other_active_rule.pk),
                    ],
                },
            ],
        }
        rule.save()
        rule.clean()
        self.assertMatches(rule, {self.matching, self.also_matching})

    def test_inactive_included_rule_still_counts(self):
        self.active_rule.active = False
        self.active_rule.save()
        rule = make_combined_rule("or", [self.active_rule.pk])
        self.assertMatches(rule, {self.matching, self.also_matching})

    def test_valid_definition(self):
        make_combined_rule("or", [self.active_rule.pk]).clean()

    def test_invalid_definitions(self):
        for definition in (
            {"operator": "xor", "rule_ids": [str(self.active_rule.pk)]},
            {"operator": "or", "rule_ids": []},
            {"operator": "or"},
            {"operator": "or", "rule_ids": str(self.active_rule.pk)},
            {"operator": "or", "rule_ids": ["not a uuid"]},
            {"operator": "or", "rule_ids": [str(uuid.uuid4())]},
            {
                "operator": "or",
                "rule_ids": [str(self.active_rule.pk)],
                "exclude_rule_ids": [str(uuid.uuid4())],
            },
            {"operator": "or", "groups": ["not a group"]},
            {"operator": "or", "groups": [{"operator": "and"}]},
            {
                "operator": "or",
                "groups": [{"operator": "xor", "rule_ids": [str(self.active_rule.pk)]}],
            },
            {
                "operator": "or",
                "groups": [{"operator": "and", "rule_ids": [str(uuid.uuid4())]}],
            },
        ):
            with self.subTest(definition=definition):
                rule = make_combined_rule("or", [self.active_rule.pk])
                rule.definition = definition
                with self.assertRaises(ValidationError):
                    rule.clean()

    def test_rejects_including_itself(self):
        rule = make_combined_rule("or", [self.active_rule.pk])
        rule.definition["rule_ids"].append(str(rule.pk))
        with self.assertRaisesMessage(ValidationError, "cannot include itself"):
            rule.clean()

    def test_rejects_indirect_cycle(self):
        inner = make_combined_rule("or", [self.active_rule.pk])
        outer = make_combined_rule("or", [inner.pk])
        inner.definition["exclude_rule_ids"] = [str(outer.pk)]
        with self.assertRaisesMessage(ValidationError, "cannot include itself"):
            inner.clean()

    def test_rejects_cycle_through_a_group(self):
        inner = make_combined_rule("or", [self.active_rule.pk])
        outer = make_combined_rule("or", [inner.pk])
        inner.definition["groups"] = [
            {"operator": "and", "rule_ids": [str(self.active_rule.pk), str(outer.pk)]}
        ]
        with self.assertRaisesMessage(ValidationError, "cannot include itself"):
            inner.clean()

    def test_clean_definition_keeps_lists(self):
        definition = CombinedRule.clean_definition(
            {"operator": "and", "rule_ids": [self.active_rule.pk]},
            CombinedRule.rule_type.definition_keys,
        )
        self.assertEqual(
            definition,
            {
                "operator": "and",
                "rule_ids": [str(self.active_rule.pk)],
                "groups": [],
                "exclude_rule_ids": [],
            },
        )

    def test_clean_definition_cleans_groups(self):
        definition = CombinedRule.clean_definition(
            {
                "operator": "or",
                "groups": [
                    {"operator": "and", "rule_ids": [self.active_rule.pk]},
                    "not a group",
                ],
            },
            CombinedRule.rule_type.definition_keys,
        )
        self.assertEqual(
            definition["groups"],
            [
                {
                    "operator": "and",
                    "rule_ids": [str(self.active_rule.pk)],
                    "groups": [],
                    "exclude_rule_ids": [],
                },
                # Kept, so validation refuses it rather than saving a broader rule.
                "not a group",
            ],
        )

    def test_rules_that_are_not_evaluated_cannot_be_parts(self):
        not_evaluated = make_rule(
            modulename="queryset_rule.py", classname="QuerySetRule"
        )
        rule = make_combined_rule("or", [self.active_rule.pk], [not_evaluated.pk])
        with self.assertRaisesMessage(ValidationError, "can't be part of"):
            rule.clean()
        with self.assertRaisesMessage(ValidationError, "can't be part of"):
            rule.matches_resource(self.matching)

    def test_each_part_is_evaluated_once(self):
        # Each level includes the one below twice, directly and through a group.
        rule = make_combined_rule("or", [self.active_rule.pk])
        for _level in range(3):
            wrapper = make_combined_rule("and", [rule.pk])
            rule = make_combined_rule("and", [rule.pk, wrapper.pk])
        # One load per level, then the lifecycle rule's own lookups.
        with self.assertNumQueries(6):
            rule.matches_resource(self.matching)
        with self.assertNumQueries(6):
            str(rule.get_matching_resources().query)

    def test_a_loop_saved_anyway_matches_nothing(self):
        first = make_combined_rule("or", [self.active_rule.pk])
        second = make_combined_rule("or", [first.pk])
        first.definition["rule_ids"].append(str(second.pk))
        first.save()
        for evaluate in (
            lambda: first.matches_resource(self.non_matching),
            first.get_matching_resources,
            first.get_search_filter_for_rule,
        ):
            with self.subTest(evaluate=evaluate):
                with self.assertRaisesMessage(ValidationError, "cannot include itself"):
                    evaluate()


class CombinedRuleGrantTests(LifecycleTestCase):
    def setUp(self):
        self.framework = ArchesAbacPermissionFramework()
        self.group = Group.objects.create(name="combined group")
        self.user = User.objects.create(username="combined user")
        self.user.groups.add(self.group)

    def grant(self, rule):
        grant = InclusionRuleGroupPermission.objects.create(rule=rule, group=self.group)
        grant.permissions.set(
            Permission.objects.filter(codename="view_resourceinstance")
        )

    def test_grant_follows_the_combination(self):
        active = self.make_lifecycle_rule()
        draft = self.make_lifecycle_rule(state=self.draft_state)
        self.grant(make_combined_rule("or", [active.pk, draft.pk], [draft.pk]))
        self.assertIn(
            "view_resourceinstance", self.framework.get_perms(self.user, self.matching)
        )
        self.assertNotIn(
            "view_resourceinstance",
            self.framework.get_perms(self.user, self.non_matching),
        )

    def test_deleted_excluded_rule_matches_nothing(self):
        active = self.make_lifecycle_rule()
        excluded = self.make_lifecycle_rule(state=self.draft_state)
        self.grant(make_combined_rule("or", [active.pk], [excluded.pk]))
        excluded.delete()
        with self.assertLogs(
            "arches_abac_permissions.permissions.arches_abac_permission_framework"
        ):
            self.assertNotIn(
                "view_resourceinstance",
                self.framework.get_perms(self.user, self.matching),
            )
            self.assertFalse(
                self.framework.filter_resource_queryset(
                    self.user, ResourceInstance.objects.all()
                ).exists()
            )


class CombinedSearchFilterTests(LifecycleTestCase):
    def setUp(self):
        self.active = self.make_lifecycle_rule()
        self.draft = self.make_lifecycle_rule(state=self.draft_state)
        self.active_filter = dsl(self.active.get_search_filter_for_rule())
        self.draft_filter = dsl(self.draft.get_search_filter_for_rule())

    def test_operators_and_exclusions(self):
        either = make_combined_rule("or", [self.active.pk, self.draft.pk])
        self.assertEqual(
            dsl(either.get_search_filter_for_rule())["bool"]["should"],
            [self.active_filter, self.draft_filter],
        )
        both = dsl(
            make_combined_rule(
                "and", [self.active.pk], [self.draft.pk]
            ).get_search_filter_for_rule()
        )
        self.assertEqual(both["bool"]["filter"], [self.active_filter])
        self.assertEqual(both["bool"]["must_not"], [self.draft_filter])

    def test_groups(self):
        rule = make_combined_rule("or", [self.draft.pk])
        rule.definition["groups"] = [
            {
                "operator": "and",
                "rule_ids": [str(self.active.pk)],
                "exclude_rule_ids": [str(self.draft.pk)],
            }
        ]
        rule.save()
        should = dsl(rule.get_search_filter_for_rule())["bool"]["should"]
        self.assertEqual(should[0], self.draft_filter)
        self.assertEqual(should[1]["bool"]["filter"], [self.active_filter])
        self.assertEqual(should[1]["bool"]["must_not"], [self.draft_filter])
        self.assertTrue(rule.has_search_filter_for_rule())

    def test_a_part_without_a_filter_leaves_the_combination_out(self):
        no_filter = make_rule(
            modulename="tile_node_value_rule.py", classname="TileNodeValueRule"
        )
        nested = make_combined_rule("or", [self.active.pk])
        nested.definition["groups"] = [
            {"operator": "or", "rule_ids": [str(no_filter.pk)]}
        ]
        nested.save()
        for rule in (
            make_combined_rule("or", [self.active.pk, no_filter.pk]),
            make_combined_rule("or", [self.active.pk], [no_filter.pk]),
            nested,
        ):
            with self.subTest(definition=rule.definition):
                self.assertIsNone(rule.get_search_filter_for_rule())
                self.assertFalse(rule.has_search_filter_for_rule())

    def test_an_empty_part_filter_leaves_the_combination_out(self):
        rule = make_combined_rule("and", [self.active.pk, self.draft.pk])
        with mock.patch.object(
            LifecycleStateRule, "get_search_filter", return_value=Bool()
        ):
            self.assertIsNone(rule.get_search_filter_for_rule())
