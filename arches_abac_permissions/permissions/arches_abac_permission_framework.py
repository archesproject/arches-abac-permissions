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

import logging
from collections import defaultdict

from django.contrib.auth.models import Group, User
from django.db import DatabaseError
from django.db.models import Q

from arches.app.models.models import ResourceInstance
from arches.app.permissions.arches_default_deny import (
    ArchesDefaultDenyPermissionFramework,
)
from arches.app.search.elasticsearch_dsl_builder import Bool
from arches.app.search.search import SearchEngine

logger = logging.getLogger(__name__)


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

    def evaluate_rule(self, rule, evaluate, default):
        """Run evaluate(rule), treating a rule that raises as matching nothing."""
        try:
            return evaluate(rule)
        except DatabaseError:
            raise
        except Exception:
            logger.exception(
                "Inclusion rule %s (%s) could not be evaluated and is being "
                "treated as matching nothing.",
                rule.pk,
                rule.name,
            )
            return default

    def get_abac_perms(
        self, user_or_group: User | Group | None, obj: ResourceInstance
    ) -> set[str]:
        """
        Return the permission codenames that ``user_or_group`` is granted on
        ``obj`` by the inclusion rules assigned to its groups.

        A group grants a permission only if ``obj`` matches every active rule
        of that group granting it; groups are OR'd.
        """
        from arches_abac_permissions.models import InclusionRuleGroupPermission

        grants = (
            InclusionRuleGroupPermission.objects.filter(
                group__in=self.get_groups(user_or_group), rule__active=True
            )
            .select_related("rule")
            .prefetch_related("permissions")
        )
        rules_by_group_perm = defaultdict(list)
        for grant in grants:
            for permission in grant.permissions.all():
                rules_by_group_perm[(grant.group_id, permission.codename)].append(
                    grant.rule
                )

        matched = {}

        def rule_matches(rule):
            if rule.pk not in matched:
                matched[rule.pk] = self.evaluate_rule(
                    rule, lambda r: r.matches_resource(obj), default=False
                )
            return matched[rule.pk]

        perms = set()
        for (_group_id, codename), rules in rules_by_group_perm.items():
            if codename not in perms and all(rule_matches(rule) for rule in rules):
                perms.add(codename)
        return perms

    def get_abac_resources(self, user: User, permission: str):
        """
        Return the resource instances on which ``user`` is granted
        ``permission`` (a codename, optionally prefixed "app_label.") by the
        inclusion rules assigned to its groups.

        Within a group, the rules granting ``permission`` are AND'd; groups
        are OR'd.
        """
        from arches_abac_permissions.models import InclusionRuleGroupPermission

        app_label, _, codename = permission.rpartition(".")
        grant_filter = Q(
            rule__active=True,
            group__in=self.get_groups(user),
            permissions__codename=codename,
        )
        if app_label:
            grant_filter &= Q(permissions__content_type__app_label=app_label)

        rules_by_group = defaultdict(list)
        grants = (
            InclusionRuleGroupPermission.objects.filter(grant_filter)
            .select_related("rule")
            .distinct()
        )
        for grant in grants:
            rules_by_group[grant.group_id].append(grant.rule)

        matching_by_rule = {}
        matches = Q()
        for rules in rules_by_group.values():
            group_matches = Q()
            for rule in rules:
                if rule.pk not in matching_by_rule:
                    matching_by_rule[rule.pk] = self.evaluate_rule(
                        rule, lambda r: r.get_matching_resources(), default=None
                    )
                matching = matching_by_rule[rule.pk]
                # A rule that can't be evaluated matches nothing.
                if matching is None:
                    break
                group_matches &= Q(pk__in=matching.values("pk"))
            else:
                matches |= group_matches
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
