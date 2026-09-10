"""
ARCHES - a program developed to inventory and manage immovable cultural heritage.
Copyright (C) 2013 J. Paul Getty Trust and World Monuments Fund

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

from django.test import SimpleTestCase

from arches.app.permissions.arches_default_deny import (
    ArchesDefaultDenyPermissionFramework,
)
from arches.app.utils.permission_backend import _get_permission_framework
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)


class AbacPermissionFrameworkTests(SimpleTestCase):
    def test_is_a_default_deny_framework(self):
        self.assertTrue(
            issubclass(
                ArchesAbacPermissionFramework, ArchesDefaultDenyPermissionFramework
            )
        )
        self.assertTrue(ArchesAbacPermissionFramework.is_exclusive)

    def test_settings_resolve_to_abac_framework(self):
        self.assertIsInstance(
            _get_permission_framework(), ArchesAbacPermissionFramework
        )

    def test_abac_rule_hooks_default_deny(self):
        framework = ArchesAbacPermissionFramework()
        self.assertEqual(framework.get_abac_rules(None), [])
        self.assertFalse(
            framework.evaluate_abac_rules(None, None, "view_resourceinstance")
        )
