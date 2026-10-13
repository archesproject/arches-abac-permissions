import json
from unittest import mock

from django.contrib.auth.models import Group, Permission, User
from django.test import SimpleTestCase, override_settings

from arches.app.search.elasticsearch_dsl_builder import Query
from arches.app.search.mappings import RESOURCES_INDEX
from arches.app.search.search_term import TermSearch
from arches_abac_permissions.apps import (
    CORE_TERM_SEARCH,
    PERMITTED_TERM_SEARCH,
    check_term_search,
)
from arches_abac_permissions.permitted_term_search import PermittedTermSearch

from tests.test_inclusion_rules import LifecycleTestCase

TERMS = {"key": "terms"}


class PermittedTermSearchTests(LifecycleTestCase):
    def setUp(self):
        self.group = Group.objects.create(name="Readers")
        self.user = User.objects.create(username="reader")
        self.user.groups.add(self.group)
        self.user.user_permissions.add(
            Permission.objects.get(codename="read_nodegroup")
        )

    def search(self, user, buckets=()):
        sent = {}

        def fake_search(query, index="", **kwargs):
            sent["index"], sent["dsl"] = index, query.dsl
            return {
                "aggregations": {
                    "strings": {"matching": {"value_agg": {"buckets": list(buckets)}}}
                }
            }

        with mock.patch.object(Query, "search", autospec=True, side_effect=fake_search):
            suggestions = PermittedTermSearch.search_terms("belf", "en", user, TERMS)
        return suggestions, sent

    def test_searches_resources_under_the_permission_filter(self):
        _, sent = self.search(self.user)
        self.assertEqual(sent["index"], RESOURCES_INDEX)
        filters = sent["dsl"]["query"]["bool"]["filter"]
        self.assertEqual(filters[0]["nested"]["path"], "strings")
        permission_filter = json.dumps(filters[1])
        self.assertIn("permissions.groups_read", permission_filter)
        self.assertIn(str(self.group.pk), permission_filter)

    def test_returns_suggestions_in_core_shape(self):
        bucket = {
            "key": "Belfast Castle",
            "nodegroupid": {"buckets": [{"key": str(self.nodegroup.pk)}]},
        }
        suggestions, _ = self.search(self.user, buckets=[bucket])
        self.assertEqual(
            suggestions,
            [
                {
                    "type": "term",
                    "context": "",
                    "context_label": " - ",
                    "id": "terms0",
                    "text": "Belfast Castle",
                    "value": "Belfast Castle",
                    "nodegroupid": str(self.nodegroup.pk),
                }
            ],
        )

    def test_superuser_uses_core_term_search(self):
        admin = User.objects.create(username="superuser", is_superuser=True)
        with mock.patch.object(TermSearch, "search_terms", return_value=[]) as core:
            PermittedTermSearch.search_terms("belf", "en", admin, TERMS)
        core.assert_called_once_with("belf", "en", admin, TERMS)


class TermSearchCheckTests(SimpleTestCase):
    def term_search(self, module):
        return [{"type": "term", "key": "terms", "module": module}]

    def test_warns_while_core_term_search_is_configured(self):
        with override_settings(TERM_SEARCH_TYPES=self.term_search(CORE_TERM_SEARCH)):
            self.assertEqual(
                [w.id for w in check_term_search(None)],
                ["arches_abac_permissions.W001"],
            )

    def test_silent_with_permitted_term_search(self):
        with override_settings(
            TERM_SEARCH_TYPES=self.term_search(PERMITTED_TERM_SEARCH)
        ):
            self.assertEqual(check_term_search(None), [])
