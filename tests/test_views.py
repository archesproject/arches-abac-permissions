import json
import uuid
from unittest import skipIf, skipUnless
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import Group, Permission, User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from arches.app.models.models import (
    ETLModule,
    GraphXPublishedGraph,
    LoadEvent,
    UserProfile,
)
from arches_abac_permissions.rule_types import ANONYMOUS_USERNAME
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
            reverse("abac_user", args=[self.user.pk]),
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

    def test_rule_type_matches_module_and_class(self):
        make_rule(modulename="other_rule.py", classname="LifecycleStateRule")
        self.assertEqual(self.client.get(reverse("abac_rules")).json()["rules"], [])

    def test_unsupported_rule_types_not_editable(self):
        rule = make_rule(modulename="search_rule.py", classname="SearchRule")
        url = reverse("abac_rule", args=[rule.pk])
        self.assertEqual(self.send("get", url).status_code, 404)
        self.assertEqual(self.send("put", url, self.payload()).status_code, 404)
        self.assertEqual(self.send("delete", url).status_code, 404)
        self.assertTrue(InclusionRule.objects.filter(pk=rule.pk).exists())

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
        expected += ["spatial", "tile_node_value"]
        self.assertEqual([t["key"] for t in types], expected)

    def test_resource_sets(self):
        response = self.client.get(reverse("abac_resource_sets"))
        self.assertEqual(response.status_code, 200)
        if not apps.is_installed("arches_resource_sets"):
            self.assertEqual(response.json()["resource_sets"], [])

    @skipUnless(apps.is_installed("arches_resource_sets"), "needs resource sets")
    def test_resource_sets_names(self):
        from arches_resource_sets.models import ResourceSet

        unnamed = ResourceSet.objects.create(
            id="00000000-0000-0000-0000-000000000001", owner=self.superuser
        )
        named = ResourceSet.objects.create(owner=self.superuser, name="Zebras")
        resource_sets = self.client.get(reverse("abac_resource_sets")).json()[
            "resource_sets"
        ]
        self.assertEqual(
            resource_sets,
            [
                {"id": str(unnamed.pk), "name": ""},
                {"id": str(named.pk), "name": "Zebras"},
            ],
        )

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

    def test_list_flags_and_counts(self):
        self.group.user_set.add(self.user, self.superuser)
        groups = {
            g["name"]: g
            for g in self.send("get", reverse("abac_groups")).json()["groups"]
        }
        self.assertEqual(groups["Reviewers"]["member_count"], 2)
        self.assertFalse(groups["Reviewers"]["is_built_in"])
        self.assertFalse(groups["Reviewers"]["is_public"])
        self.assertTrue(groups["Guest"]["is_built_in"])
        self.assertTrue(groups["Guest"]["is_public"])

    def test_group_with_anonymous_is_public(self):
        anonymous, _created = User.objects.get_or_create(username="anonymous")
        self.group.user_set.add(anonymous)
        groups = {
            g["name"]: g
            for g in self.send("get", reverse("abac_groups")).json()["groups"]
        }
        self.assertTrue(groups["Reviewers"]["is_public"])

    def test_delete_built_in_group_refused(self):
        guest = Group.objects.get(name="Guest")
        guest.user_set.clear()
        url = reverse("abac_group", args=[guest.pk])
        self.assertEqual(self.send("delete", url).status_code, 409)
        self.assertTrue(Group.objects.filter(pk=guest.pk).exists())

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
        self.assertNotIn("email", users["plain"])
        self.assertFalse(users["plain"]["is_public"])

    def test_user_details(self):
        self.user.email = "plain@example.org"
        self.user.save()
        response = self.send("get", reverse("abac_user", args=[self.user.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "plain@example.org")
        self.assertNotIn("password", response.json())
        missing = reverse("abac_user", args=[999999])
        self.assertEqual(self.send("get", missing).status_code, 404)

    def new_user_payload(self, **overrides):
        body = {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.org",
            "username": "Ada.L",
            "phone": "+1 650-253-0000",
        }
        body.update(overrides)
        return body

    def post_user(self, **overrides):
        return self.send(
            "post", reverse("abac_users"), self.new_user_payload(**overrides)
        )

    def test_create_user_sends_invite(self):
        response = self.post_user()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["username"], "ada.l")
        user = User.objects.get(username="ada.l")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.userprofile.phone, "+16502530000")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ada@example.org"])
        reset_path = mail.outbox[0].body.split("http://testserver")[1].split()[0]
        uidb64, token = reset_path.strip("/").split("/")[-2:]
        self.assertEqual(int(force_str(urlsafe_base64_decode(uidb64))), user.pk)
        self.assertTrue(default_token_generator.check_token(user, token))

    def test_create_user_without_phone(self):
        self.assertEqual(self.post_user(phone="").status_code, 201)
        self.assertEqual(UserProfile.objects.get(user__username="ada.l").phone, "")

    def test_create_user_rejects_duplicates_case_insensitively(self):
        self.user.email = "Plain@Example.org"
        self.user.save()
        response = self.post_user(username="PLAIN", email="plain@example.ORG")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"username", "email"})
        self.assertEqual(len(mail.outbox), 0)

    def test_create_user_rejects_invalid_fields(self):
        cases = {
            "first_name": " ",
            "last_name": "",
            "email": "not-an-email",
            "username": "a b",
            "phone": "+1 123",
        }
        for field, value in cases.items():
            response = self.post_user(**{field: value})
            self.assertEqual(response.status_code, 400, field)
            self.assertEqual(set(response.json()["errors"]), {field}, field)
        # A landline is not accepted; neither is a number without a country code.
        for phone in ("+44 20 7946 0958", "650 253 0000"):
            self.assertEqual(self.post_user(phone=phone).status_code, 400, phone)
        self.assertFalse(User.objects.filter(username="ada.l").exists())

    def test_create_user_rejects_overlong_fields(self):
        for field in ("first_name", "last_name", "email"):
            value = "x" * 300 + ("@example.org" if field == "email" else "")
            response = self.post_user(**{field: value})
            self.assertEqual(response.status_code, 400, field)
            self.assertEqual(set(response.json()["errors"]), {field}, field)

    def test_create_user_rolls_back_when_email_fails(self):
        with patch(
            "arches_abac_permissions.membership_views.EmailMultiAlternatives.send",
            side_effect=OSError("smtp down"),
        ):
            response = self.post_user()
        self.assertEqual(response.status_code, 500)
        self.assertFalse(User.objects.filter(username="ada.l").exists())
        self.assertFalse(UserProfile.objects.filter(phone="+16502530000").exists())

    def make_user(self, **overrides):
        fields = {
            "username": "target",
            "email": "t@example.org",
            "first_name": "Tia",
            "last_name": "Target",
            **overrides,
        }
        user = User.objects.create_user(password="pw", **fields)
        UserProfile.objects.update_or_create(
            user=user, defaults={"phone": "+16502530000"}
        )
        return user

    def patch_user(self, user, **body):
        return self.send("patch", reverse("abac_user", args=[user.pk]), body)

    def test_edit_keeps_unchanged_legacy_username_and_phone(self):
        target = self.make_user(username="Jane@X.org")
        UserProfile.objects.filter(user=target).update(phone="555-1234")
        body = dict(
            first_name="Janet",
            last_name="Target",
            email="t@example.org",
            username="Jane@X.org",
            phone="555-1234",
        )
        self.assertEqual(self.patch_user(target, **body).status_code, 200)
        target.refresh_from_db()
        self.assertEqual(
            (target.username, target.first_name, target.userprofile.phone),
            ("Jane@X.org", "Janet", "555-1234"),
        )
        for field, value in (("username", "Bad Name!"), ("phone", "555-12")):
            response = self.patch_user(target, **{**body, field: value})
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.json()["errors"])

    def test_public_user_cannot_be_edited_or_reset(self):
        public = User.objects.get(username=ANONYMOUS_USERNAME)
        for body in (
            {"username": "renamed"},
            {"first_name": "X"},
            {"password_action": "reset"},
        ):
            self.assertEqual(self.patch_user(public, **body).status_code, 400)
        public.refresh_from_db()
        self.assertEqual(public.username, ANONYMOUS_USERNAME)
        self.assertEqual(self.patch_user(public, is_active=True).status_code, 200)

    def test_details_include_phone_and_delete_state(self):
        target = self.make_user()
        details = self.send("get", reverse("abac_user", args=[target.pk])).json()
        self.assertEqual(details["phone"], "+16502530000")
        self.assertTrue(details["can_delete"])
        own = self.send("get", reverse("abac_user", args=[self.superuser.pk])).json()
        self.assertEqual((own["can_delete"], own["delete_block_code"]), (False, "self"))
        users = self.send("get", reverse("abac_users")).json()
        self.assertEqual(users["current_user_id"], self.superuser.pk)

    def test_edit_user_keeps_password_and_allows_own_values(self):
        target = self.make_user()
        response = self.patch_user(
            target,
            first_name="Tess",
            last_name="Target",
            email="T@example.org",
            username="TARGET",
            phone="",
        )
        self.assertEqual(response.status_code, 200, response.content)
        target.refresh_from_db()
        self.assertEqual((target.first_name, target.email), ("Tess", "T@example.org"))
        self.assertTrue(target.has_usable_password())
        self.assertEqual(target.userprofile.phone, "")
        self.assertEqual(len(mail.outbox), 0)

    def test_edit_user_sends_reset_link(self):
        target = self.make_user()
        response = self.patch_user(target, password_action="reset")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["t@example.org"])
        reset_path = mail.outbox[0].body.split("http://testserver")[1].split()[0]
        uidb64, token = reset_path.strip("/").split("/")[-2:]
        self.assertEqual(int(force_str(urlsafe_base64_decode(uidb64))), target.pk)
        self.assertTrue(default_token_generator.check_token(target, token))
        self.assertTrue(target.has_usable_password())

    def test_edit_user_validation(self):
        target = self.make_user()
        self.make_user(username="other", email="o@example.org")
        for body, field in (
            ({"email": "O@example.org"}, "email"),
            ({"username": "OTHER"}, "username"),
            ({"username": "no"}, "username"),
            ({"first_name": " "}, "first_name"),
            ({"phone": "+1 123"}, "phone"),
        ):
            response = self.patch_user(target, **body)
            self.assertEqual(response.status_code, 400, body)
            self.assertEqual(set(response.json()["errors"]), {field}, body)
        self.assertEqual(self.patch_user(target, password_action="x").status_code, 400)
        self.assertEqual(self.patch_user(target, is_active="no").status_code, 400)

    def test_edit_user_rolls_back_when_reset_email_fails(self):
        target = self.make_user()
        with patch(
            "arches_abac_permissions.membership_views.EmailMultiAlternatives.send",
            side_effect=OSError("smtp down"),
        ):
            response = self.patch_user(
                target, first_name="Changed", password_action="reset"
            )
        self.assertEqual(response.status_code, 500)
        target.refresh_from_db()
        self.assertEqual(target.first_name, "Tia")

    def test_toggle_active(self):
        target = self.make_user()
        self.assertFalse(self.patch_user(target, is_active=False).json()["is_active"])
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertTrue(self.patch_user(target, is_active=True).json()["is_active"])

    def test_cannot_deactivate_self_or_public_user(self):
        public = User.objects.get(username=ANONYMOUS_USERNAME)
        for user in (self.superuser, public):
            self.assertEqual(self.patch_user(user, is_active=False).status_code, 400)
            user.refresh_from_db()
            self.assertTrue(user.is_active)

    def test_delete_user(self):
        target = self.make_user()
        response = self.send("delete", reverse("abac_user", args=[target.pk]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(pk=target.pk).exists())
        self.assertFalse(UserProfile.objects.filter(phone="+16502530000").exists())

    def test_delete_refused(self):
        public = User.objects.get(username=ANONYMOUS_USERNAME)
        other_admin = self.make_user(username="admin2", is_superuser=True)
        for user in (self.superuser, public, other_admin):
            response = self.send("delete", reverse("abac_user", args=[user.pk]))
            self.assertEqual(response.status_code, 400)
            self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_delete_refused_for_history_owners(self):
        publisher = self.make_user(username="publisher", email="p@example.org")
        GraphXPublishedGraph.objects.create(graph=self.graph, user=publisher)
        loader = self.make_user(username="loader", email="l@example.org")
        module = ETLModule.objects.create(
            name="m", icon="i", etl_type="import", component="c", componentname="c"
        )
        LoadEvent.objects.create(user=loader, etl_module=module)
        for user in (publisher, loader):
            url = reverse("abac_user", args=[user.pk])
            response = self.send("delete", url)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["code"], "history")
            self.assertTrue(User.objects.filter(pk=user.pk).exists())
            self.assertFalse(self.send("get", url).json()["can_delete"])

    def test_user_management_requires_superuser(self):
        target = self.make_user()
        self.client.force_login(self.user)
        url = reverse("abac_user", args=[target.pk])
        for method in ("patch", "delete"):
            self.assertEqual(self.send(method, url, {}).status_code, 403)
        self.assertTrue(User.objects.filter(pk=target.pk).exists())

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
