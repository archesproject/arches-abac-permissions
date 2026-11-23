from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.urls import reverse

from arches_abac_permissions.models import InclusionRuleGroupPermission, NestedGroup
from arches_abac_permissions.nested_groups import get_parents, inheritance_links, walk
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)
from tests.test_inclusion_rules import LifecycleTestCase
from tests.test_views import ApiTestCase


class NestedGroupTestCase(LifecycleTestCase):
    """Team sits inside Department, which sits inside Organisation."""

    def setUp(self):
        self.framework = ArchesAbacPermissionFramework()
        self.organisation = Group.objects.create(name="Organisation")
        self.department = Group.objects.create(name="Department")
        self.team = Group.objects.create(name="Team")
        NestedGroup.objects.create(group=self.department, parent=self.organisation)
        NestedGroup.objects.create(group=self.team, parent=self.department)

    def grant_view(self, group):
        grant = InclusionRuleGroupPermission.objects.create(
            rule=self.make_lifecycle_rule(), group=group
        )
        grant.permissions.set(
            Permission.objects.filter(codename="view_resourceinstance")
        )

    def member_of(self, group):
        user = User.objects.create(username=f"member of {group.name}")
        user.groups.add(group)
        return user

    def can_read(self, user):
        return self.framework.user_can_read_resource(user, resource=self.matching)


@override_settings(ABAC_NESTED_GROUP_INHERITANCE="from_parents")
class NestedGroupInheritanceTests(NestedGroupTestCase):
    def test_from_parents_gives_inner_groups_outer_groups_rules(self):
        self.grant_view(self.organisation)
        self.assertTrue(self.can_read(self.member_of(self.team)))
        self.assertTrue(self.can_read(self.member_of(self.department)))

    def test_from_parents_does_not_flow_outwards(self):
        self.grant_view(self.team)
        self.assertFalse(self.can_read(self.member_of(self.department)))
        self.assertFalse(self.can_read(self.member_of(self.organisation)))

    @override_settings(ABAC_NESTED_GROUP_INHERITANCE="from_children")
    def test_from_children_gives_outer_groups_inner_groups_rules(self):
        self.grant_view(self.team)
        self.assertTrue(self.can_read(self.member_of(self.organisation)))
        self.assertTrue(self.can_read(self.member_of(self.department)))

    @override_settings(ABAC_NESTED_GROUP_INHERITANCE="from_children")
    def test_from_children_does_not_flow_inwards(self):
        self.grant_view(self.organisation)
        self.assertFalse(self.can_read(self.member_of(self.team)))

    def test_group_checks_include_nesting(self):
        self.grant_view(self.organisation)
        self.assertTrue(
            self.framework.has_group_perm(
                self.team, "view_resourceinstance", self.matching
            )
        )

    def test_without_nesting_groups_are_the_django_groups(self):
        NestedGroup.objects.all().delete()
        user = self.member_of(self.team)
        # One query, for the nesting links; the groups stay a lazy queryset.
        with self.assertNumQueries(1):
            groups = self.framework.get_groups(user)
        self.assertEqual(list(groups), [self.team])
        self.assertEqual(list(self.framework.get_groups(self.team)), [self.team])

    def test_walk_lists_groups_nearest_first(self):
        self.assertEqual(
            walk([self.team.pk], get_parents()),
            [self.department.pk, self.organisation.pk],
        )
        with self.settings(ABAC_NESTED_GROUP_INHERITANCE="from_children"):
            self.assertEqual(
                walk([self.organisation.pk], inheritance_links()),
                [self.department.pk, self.team.pk],
            )

    @override_settings(ABAC_NESTED_GROUP_INHERITANCE="sideways")
    def test_unknown_direction_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            inheritance_links()


@override_settings(ABAC_NESTED_GROUP_INHERITANCE="from_parents")
class NestedGroupApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.outer = Group.objects.create(name="Outer")
        self.inner = Group.objects.create(name="Inner")

    def set_parents(self, group, parent_ids):
        return self.send(
            "put", reverse("abac_group", args=[group.pk]), {"parent_ids": parent_ids}
        )

    def listed(self):
        groups = self.send("get", reverse("abac_groups")).json()["groups"]
        return {group["name"]: group for group in groups}

    def test_set_parents_and_list_inheritance(self):
        response = self.set_parents(self.inner, [self.outer.pk])
        self.assertEqual(response.status_code, 200, response.content)
        groups = self.listed()
        self.assertEqual(groups["Inner"]["parent_ids"], [self.outer.pk])
        self.assertEqual(groups["Inner"]["inherits_from_ids"], [self.outer.pk])
        self.assertEqual(groups["Outer"]["inherits_from_ids"], [])

    @override_settings(ABAC_NESTED_GROUP_INHERITANCE="from_children")
    def test_inheritance_follows_the_setting(self):
        self.set_parents(self.inner, [self.outer.pk])
        groups = self.listed()
        self.assertEqual(groups["Outer"]["inherits_from_ids"], [self.inner.pk])
        self.assertEqual(groups["Inner"]["inherits_from_ids"], [])

    def test_replacing_parents_removes_old_links(self):
        self.set_parents(self.inner, [self.outer.pk])
        self.set_parents(self.inner, [])
        self.assertFalse(NestedGroup.objects.exists())

    def test_rejects_loops_and_unknown_groups(self):
        self.set_parents(self.inner, [self.outer.pk])
        for group, parent_ids in (
            (self.inner, [self.inner.pk]),
            (self.outer, [self.inner.pk]),
            (self.inner, [999999]),
        ):
            response = self.set_parents(group, parent_ids)
            self.assertEqual(response.status_code, 400, parent_ids)
        self.assertEqual(NestedGroup.objects.count(), 1)

    def test_parent_ids_are_required(self):
        self.set_parents(self.inner, [self.outer.pk])
        response = self.send("put", reverse("abac_group", args=[self.inner.pk]), {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(NestedGroup.objects.count(), 1)

    def test_group_with_groups_inside_it_cannot_be_deleted(self):
        self.set_parents(self.inner, [self.outer.pk])
        response = self.send("delete", reverse("abac_group", args=[self.outer.pk]))
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Group.objects.filter(pk=self.outer.pk).exists())
        # The inner group has nothing inside it, so it can go.
        response = self.send("delete", reverse("abac_group", args=[self.inner.pk]))
        self.assertEqual(response.status_code, 204)

    def test_unknown_group(self):
        response = self.send(
            "put", reverse("abac_group", args=[999999]), {"parent_ids": []}
        )
        self.assertEqual(response.status_code, 404)


class NestedGroupsOffTests(NestedGroupTestCase):
    """Nesting is off unless ABAC_NESTED_GROUP_INHERITANCE turns it on."""

    def test_links_are_ignored_without_a_query(self):
        self.grant_view(self.organisation)
        user = self.member_of(self.team)
        with self.assertNumQueries(0):
            groups = self.framework.get_groups(user)
        self.assertEqual(list(groups), [self.team])
        self.assertFalse(self.can_read(user))


class NestedGroupsOffApiTests(ApiTestCase):
    def test_groups_report_nesting_off_and_parents_cannot_be_set(self):
        self.assertEqual(
            self.send("get", reverse("abac_groups")).json()["nesting"], "off"
        )
        outer = Group.objects.create(name="Outer")
        response = self.send(
            "put",
            reverse("abac_group", args=[self.group.pk]),
            {"parent_ids": [outer.pk]},
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(NestedGroup.objects.exists())
