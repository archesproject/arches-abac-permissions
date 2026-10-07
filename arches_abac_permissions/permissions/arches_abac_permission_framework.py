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

from __future__ import annotations

from django.contrib.auth.models import Group, User

from arches.app.models.models import ResourceInstance
from arches.app.permissions.arches_default_deny import (
    ArchesDefaultDenyPermissionFramework,
)
from arches.app.search.elasticsearch_dsl_builder import Bool
from arches.app.search.search import SearchEngine


class ArchesAbacPermissionFramework(ArchesDefaultDenyPermissionFramework):
    """
    Attribute-based access control (ABAC) permission framework.

    This starts from Arches' default-deny behavior: a user or group has no
    access to a resource instance unless permission is explicitly granted.
    The methods below are the seams where ABAC rules (e.g. evaluating tile
    values, lifecycle state, spatial extent, or other resource/user
    attributes) will be layered on top of that baseline in the future.

    None of the attribute evaluation is implemented yet - each hook below
    currently just defers to the default-deny behavior, so installing this
    framework today is equivalent to using
    ``ArchesDefaultDenyPermissionFramework`` directly. As rules are added,
    ``get_abac_rules`` and ``evaluate_abac_rules`` are the entry points to
    extend.
    """

    def get_abac_rules(self, user_or_group: User | Group) -> list:
        """
        Return the ABAC rules/policies that apply to the given user or
        group.

        TODO: implement rule retrieval (e.g. from a rule configuration
        model) once the ABAC rule schema is defined.
        """
        return []

    def evaluate_abac_rules(
        self, user_or_group: User | Group, obj: ResourceInstance, action: str
    ) -> bool:
        """
        Evaluate whether ``user_or_group`` is granted ``action`` on ``obj``
        based on ABAC rules.

        TODO: implement attribute evaluation. Until then this always denies,
        preserving default-deny behavior.
        """
        return False

    def get_filtered_instances(
        self,
        user: User,
        search_engine: SearchEngine | None = None,
        allresources: bool = False,
        resources: list[str] | None = None,
    ):
        # TODO: merge in resources granted via ABAC rules once implemented.
        return super().get_filtered_instances(
            user, search_engine, allresources, resources
        )

    def get_permission_search_filter(self, user: User) -> Bool:
        # TODO: OR in an ABAC-derived search filter once rule evaluation
        # exists.
        return super().get_permission_search_filter(user)

    def get_perms(
        self, user_or_group: User | Group, obj: ResourceInstance
    ) -> list[str]:
        perms = super().get_perms(user_or_group, obj)
        # TODO: extend `perms` with any actions granted by ABAC rules.
        return perms

    def has_group_perm(self, group: Group, perm: str, obj: ResourceInstance) -> bool:
        if super().has_group_perm(group, perm, obj):
            return True
        return self.evaluate_abac_rules(group, obj, perm)
