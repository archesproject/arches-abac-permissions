"""Re-index the resources a rule matches, after its definition or grants change."""

from arches.app.models.resource import Resource
from arches.app.utils.index_database import index_resources_using_singleprocessing
from arches_abac_permissions.permissions.arches_abac_permission_framework import (
    ArchesAbacPermissionFramework,
)


def rule_matches(rule):
    """Ids of the resources a rule matches; empty if the rule can't be evaluated."""
    matching = ArchesAbacPermissionFramework().evaluate_rule(
        rule, lambda r: r.get_matching_resources(), default=None
    )
    return set() if matching is None else set(matching.values_list("pk", flat=True))


# Runs in-process, so a rule matching many resources makes the caller wait.
def reindex_resources(resource_ids):
    if resource_ids:
        index_resources_using_singleprocessing(
            Resource.objects.filter(pk__in=resource_ids), quiet=True
        )
