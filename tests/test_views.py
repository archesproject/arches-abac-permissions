import json
import uuid
from unittest import skipIf

from django.apps import apps
from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse

from arches_abac_permissions.models import InclusionRule, InclusionRuleGroupPermission
from tests.test_inclusion_rules import LifecycleTestCase, make_rule


class ApiTestCase(LifecycleTestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser("api_admin", password="pw")
        self.user = User.objects.create_user("plain", password="pw")
        self.group = Group.objects.create(name="Reviewers")
        self.client.force_login(self.superuser)

    def payload(self, **overrides):
        body = {
            "name": "Active resources",
            "description": "desc",
            "active": True,
            "rule_type": "lifecycle_state",
            "definition": {
                "graphid": str(self.graph.pk),
                "lifecycle_state_id": str(self.active_state.pk),
            },
            "group_permissions": [
                {"groupid": self.group.pk, "permissions": ["read", "update"]}
            ],
        }
        body.update(overrides)
        return body

    def send(self, method, url, body=None):
        if method == "get":
            return self.client.get(url)
        return getattr(self.client, method)(
            url,
            data=json.dumps(body) if body is not None else None,
            content_type="application/json",
        )

    def create_rule(self, **overrides):
        response = self.send("post", reverse("abac_rules"), self.payload(**overrides))
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()


class AccessTests(ApiTestCase):
    def urls(self):
        rule = make_rule(
            modulename="lifecycle_state_rule.py", classname="LifecycleStateRule"
        )
        return [
            reverse("abac_rules"),
            reverse("abac_rule", args=[rule.pk]),
            reverse("abac_rule_types"),
            reverse("abac_resource_models"),
            reverse("abac_resource_model_nodes", args=[self.graph.pk]),
            reverse("abac_languages"),
            reverse("abac_map_config"),
            reverse("abac_controlled_list_items", args=[uuid.uuid4()]),
            reverse("abac_groups"),
            reverse("abac_group", args=[self.group.pk]),
            reverse("abac_users"),
            reverse("abac_user_group_membership"),
        ]

    def test_non_superuser_forbidden(self):
        self.client.force_login(self.user)
        for url in self.urls():
            for method in ("get", "post", "put", "delete"):
                response = self.send(method, url, {})
                self.assertEqual(response.status_code, 403, (method, url))
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())

    def test_anonymous_forbidden(self):
        self.client.logout()
        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code, 403)


class RuleApiTests(ApiTestCase):
    def test_create_and_get(self):
        created = self.create_rule()
        self.assertEqual(created["rule_type"], "lifecycle_state")
        self.assertEqual(
            created["group_permissions"],
            [{"groupid": self.group.pk, "permissions": ["read", "update"]}],
        )
        rule = InclusionRule.objects.get(pk=created["id"])
        self.assertEqual(rule.classname, "LifecycleStateRule")
        self.assertEqual(rule.owner, self.superuser)
        grant = rule.group_permissions.get()
        self.assertEqual(
            {p.codename for p in grant.permissions.all()},
            {"view_resourceinstance", "change_resourceinstance"},
        )
        listed = self.client.get(reverse("abac_rules")).json()["rules"]
        self.assertEqual([r["id"] for r in listed], [created["id"]])

    def test_list_excludes_unsupported_rule_types(self):
        make_rule(modulename="search_rule.py", classname="SearchRule")
        self.assertEqual(self.client.get(reverse("abac_rules")).json()["rules"], [])

    def test_update_replaces_grants(self):
        other = Group.objects.create(name="Other")
        created = self.create_rule()
        url = reverse("abac_rule", args=[created["id"]])
        body = self.payload(
            name="Renamed",
            active=False,
            group_permissions=[
                {"groupid": self.group.pk, "permissions": []},
                {"groupid": other.pk, "permissions": ["delete"]},
            ],
        )
        response = self.send("put", url, body)
        self.assertEqual(response.status_code, 200, response.content)
        rule = InclusionRule.objects.get(pk=created["id"])
        self.assertEqual(rule.name, "Renamed")
        self.assertFalse(rule.active)
        self.assertEqual(
            response.json()["group_permissions"],
            [{"groupid": other.pk, "permissions": ["delete"]}],
        )
        self.assertEqual(InclusionRuleGroupPermission.objects.count(), 1)

    def test_delete(self):
        created = self.create_rule()
        url = reverse("abac_rule", args=[created["id"]])
        self.assertEqual(self.send("delete", url).status_code, 204)
        self.assertEqual(self.send("delete", url).status_code, 404)
        self.assertFalse(InclusionRule.objects.exists())

    def test_validation_errors(self):
        bad_payloads = [
            {"name": " "},
            {"rule_type": "other"},
            {"definition": {}},
            {"definition": {"graphid": "nope", "lifecycle_state_id": "nope"}},
            {
                "definition": {
                    "graphid": str(self.graph.pk),
                    "lifecycle_state_id": str(self.other_lifecycle_state.pk),
                }
            },
            {"group_permissions": [{"groupid": 0, "permissions": ["read"]}]},
            {
                "group_permissions": [
                    {"groupid": self.group.pk, "permissions": ["create"]}
                ]
            },
            {"active": "yes"},
        ]
        for overrides in bad_payloads:
            response = self.send(
                "post", reverse("abac_rules"), self.payload(**overrides)
            )
            self.assertEqual(response.status_code, 400, overrides)
        response = self.client.post(
            reverse("abac_rules"), data="[", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(InclusionRule.objects.exists())

    def test_failed_update_changes_nothing(self):
        created = self.create_rule()
        url = reverse("abac_rule", args=[created["id"]])
        response = self.send("put", url, self.payload(name="X", definition={}))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(InclusionRule.objects.get().name, "Active resources")

    def test_client_cannot_choose_rule_class(self):
        created = self.create_rule(modulename="search_rule.py", classname="SearchRule")
        self.assertEqual(
            InclusionRule.objects.get(pk=created["id"]).classname, "LifecycleStateRule"
        )


class ReferenceDataApiTests(ApiTestCase):
    def test_rule_types(self):
        types = self.client.get(reverse("abac_rule_types")).json()["rule_types"]
        expected = ["lifecycle_state"]
        if apps.is_installed("arches_resource_sets"):
            expected.append("resource_set")
        expected += ["tile_node_value", "spatial"]
        self.assertEqual([t["key"] for t in types], expected)

    def test_resource_sets(self):
        response = self.client.get(reverse("abac_resource_sets"))
        self.assertEqual(response.status_code, 200)
        if not apps.is_installed("arches_resource_sets"):
            self.assertEqual(response.json()["resource_sets"], [])

    @skipIf(apps.is_installed("arches_resource_sets"), "resource sets installed")
    def test_resource_set_rule_unavailable_without_app(self):
        response = self.send(
            "post",
            reverse("abac_rules"),
            self.payload(
                rule_type="resource_set",
                definition={"resource_set_id": str(uuid.uuid4())},
            ),
        )
        self.assertEqual(response.status_code, 400)

    def test_resource_models(self):
        models = self.client.get(reverse("abac_resource_models")).json()[
            "resource_models"
        ]
        by_id = {m["graphid"]: m for m in models}
        self.assertIn(str(self.graph.pk), by_id)
        self.assertNotIn(str(self.branch.pk), by_id)
        self.assertEqual(
            {s["id"] for s in by_id[str(self.graph.pk)]["lifecycle_states"]},
            {str(self.draft_state.pk), str(self.active_state.pk)},
        )


class GroupApiTests(ApiTestCase):
    def test_create(self):
        response = self.send("post", reverse("abac_groups"), {"name": " New group "})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Group.objects.filter(name="New group").exists())

    def test_create_validation(self):
        url = reverse("abac_groups")
        self.assertEqual(self.send("post", url, {"name": ""}).status_code, 400)
        self.assertEqual(self.send("post", url, {"name": "x" * 151}).status_code, 400)
        self.assertEqual(self.send("post", url, {"name": "Reviewers"}).status_code, 409)

    def test_delete_removes_grants(self):
        self.create_rule()
        url = reverse("abac_group", args=[self.group.pk])
        self.assertEqual(self.send("delete", url).status_code, 204)
        self.assertFalse(InclusionRuleGroupPermission.objects.exists())
        self.assertEqual(self.send("delete", url).status_code, 404)

    def test_delete_group_with_members_refused(self):
        self.group.user_set.add(self.user)
        url = reverse("abac_group", args=[self.group.pk])
        self.assertEqual(self.send("delete", url).status_code, 409)
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())


class MembershipApiTests(ApiTestCase):
    def test_list_users(self):
        self.user.groups.add(self.group)
        response = self.send("get", reverse("abac_users"))
        self.assertEqual(response.status_code, 200)
        users = {u["username"]: u for u in response.json()["users"]}
        self.assertEqual(users["plain"]["groups"], [self.group.pk])
        self.assertNotIn("password", users["plain"])

    def test_bulk_add_and_remove(self):
        other = Group.objects.create(name="Other")
        self.user.groups.add(other)
        url = reverse("abac_user_group_membership")
        response = self.send(
            "post",
            url,
            {
                "user_ids": [self.user.pk, self.superuser.pk],
                "add": [self.group.pk],
                "remove": [other.pk],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            set(self.user.groups.values_list("pk", flat=True)), {self.group.pk}
        )
        self.assertEqual(
            set(self.superuser.groups.values_list("pk", flat=True)), {self.group.pk}
        )

    def test_rejects_bad_input(self):
        url = reverse("abac_user_group_membership")
        good = {"user_ids": [self.user.pk], "add": [self.group.pk], "remove": []}
        for change in (
            {"user_ids": []},
            {"user_ids": [999999]},
            {"add": [999999]},
            {"add": ["x"]},
            {"remove": [self.group.pk]},
        ):
            response = self.send("post", url, {**good, **change})
            self.assertEqual(response.status_code, 400, change)
        self.assertEqual(self.user.groups.count(), 0)
