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
from django.db.models import Q

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
    Permissions granted to a group by an InclusionRule apply to any resource
    instance the rule matches. They are added in ``get_perms``, which drives
    the single-resource checks (``user_can_read_resource``,
    ``user_can_edit_resource``, ``user_can_delete_resource``,
    ``has_group_perm``), and in ``filter_resource_queryset``, which drives
    SQL-based search such as arches-search. Elasticsearch results are not yet
    filtered by rules.
    """

    def get_groups(self, user_or_group: User | Group | None):
        if isinstance(user_or_group, Group):
            return [user_or_group]
        if isinstance(user_or_group, User):
            return user_or_group.groups.all()
        return Group.objects.none()

    def get_abac_perms(
        self, user_or_group: User | Group | None, obj: ResourceInstance
    ) -> set[str]:
        """
        Return the permission codenames that ``user_or_group`` is granted on
        ``obj`` by the inclusion rules assigned to its groups.
        """
        from arches_abac_permissions.models import InclusionRuleGroupPermission

        grants = (
            InclusionRuleGroupPermission.objects.filter(
                group__in=self.get_groups(user_or_group)
            )
            .select_related("rule")
            .prefetch_related("permissions")
        )
        perms = set()
        for grant in grants:
            codenames = {permission.codename for permission in grant.permissions.all()}
            # Skip evaluating a rule that would grant nothing new.
            if codenames - perms and grant.rule.matches_resource(obj):
                perms |= codenames
        return perms

    def get_abac_resources(self, user: User, permission: str):
        """
        Return the resource instances on which ``user`` is granted
        ``permission`` (a codename, optionally prefixed "app_label.") by the
        inclusion rules assigned to its groups.
        """
        from arches_abac_permissions.models import InclusionRule

        app_label, _, codename = permission.rpartition(".")
        grant_filter = Q(
            group_permissions__group__in=self.get_groups(user),
            group_permissions__permissions__codename=codename,
        )
        if app_label:
            grant_filter &= Q(
                group_permissions__permissions__content_type__app_label=app_label
            )

        matches = Q()
        for rule in InclusionRule.objects.filter(grant_filter).distinct():
            matches |= Q(pk__in=rule.get_matching_resources().values("pk"))
        if not matches:
            return ResourceInstance.objects.none()
        return ResourceInstance.objects.filter(matches)

    def filter_resource_queryset(
        self,
        user: User,
        queryset,
        resourceinstance_field: str = "resourceinstanceid",
        permission: str = "models.view_resourceinstance",
    ):
        if user.is_superuser:
            return queryset

        candidates = ResourceInstance.objects.filter(
            resourceinstanceid__in=queryset.values_list(
                resourceinstance_field, flat=True
            )
        )
        permitted = super().filter_resource_queryset(
            user, candidates, permission=permission
        )
        abac_permitted = self.get_abac_resources(user, permission)

        return queryset.filter(
            Q(**{f"{resourceinstance_field}__in": permitted.values("pk")})
            | Q(**{f"{resourceinstance_field}__in": abac_permitted.values("pk")})
        )

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
        abac_perms = self.get_abac_perms(user_or_group, obj)
        return perms + sorted(abac_perms.difference(perms))
