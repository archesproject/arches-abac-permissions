import json
import uuid
from urllib.parse import quote, urlencode

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy

from arches.app.models.models import (
    GraphModel,
    ResourceInstance,
    ResourceInstanceLifecycleState,
)
from arches_abac_permissions.models import InclusionRule
from arches_abac_permissions.rule_types import RuleType


class LifecycleStateRule(InclusionRule):
    """
    Rule matching resources of a graph that are in a given lifecycle state.

    definition: {"graphid": "<graph id>", "lifecycle_state_id": "<state id>"}

    The lifecycle state must belong to the graph's resource instance lifecycle.
    """

    rule_type = RuleType(
        key="lifecycle_state",
        label=gettext_lazy("Resource has Lifecycle State"),
        description=gettext_lazy(
            "Matches resources of a resource model that are in a lifecycle state"
        ),
        icon="pi pi-sync",
        definition_keys=("graphid", "lifecycle_state_id"),
    )

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        graph_id, state_id = cls.require_ids(inclusion_rule.definition)
        filters = {
            "resource-type-filter": [{"graphid": str(graph_id), "inverted": False}],
            "lifecycle-state-filter": [{"id": str(state_id), "inverted": False}],
        }
        query = urlencode(
            {k: json.dumps(v) for k, v in filters.items()}, quote_via=quote
        )
        return f"{reverse('search_home')}?{query}"

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        ids = cls.get_ids(inclusion_rule.definition)
        if ids is None:
            return ResourceInstance.objects.none()
        graph_id, state_id = ids
        return ResourceInstance.objects.filter(
            graph_id=graph_id, resource_instance_lifecycle_state_id=state_id
        )

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        ids = cls.get_ids(inclusion_rule.definition)
        return ids is not None and ids == (
            resource.graph_id,
            resource.resource_instance_lifecycle_state_id,
        )

    @classmethod
    def validate_definition(cls, inclusion_rule):
        graph_id, state_id = cls.require_ids(inclusion_rule.definition)
        try:
            graph = GraphModel.objects.get(pk=graph_id, isresource=True)
        except GraphModel.DoesNotExist:
            raise ValidationError(
                gettext_lazy("%(graphid)s is not the id of a resource model.")
                % {"graphid": graph_id}
            )
        if not ResourceInstanceLifecycleState.objects.filter(
            pk=state_id,
            resource_instance_lifecycle_id=graph.resource_instance_lifecycle_id,
        ).exists():
            raise ValidationError(
                gettext_lazy(
                    "%(stateid)s is not the id of a lifecycle state of graph %(graphid)s."
                )
                % {"stateid": state_id, "graphid": graph_id}
            )

    @classmethod
    def get_index_sql(cls, inclusion_rule):
        # One index serves every lifecycle state rule.
        return (
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS abac_resource_graph_lifecycle_state\n"
            "    ON resource_instances (graphid, resource_instance_lifecycle_state_id);"
        )

    @staticmethod
    def get_ids(definition):
        """Return the graph and state UUIDs without touching the database."""
        try:
            return (
                uuid.UUID(str(definition["graphid"])),
                uuid.UUID(str(definition["lifecycle_state_id"])),
            )
        except (KeyError, ValueError):
            return None

    @classmethod
    def require_ids(cls, definition):
        ids = cls.get_ids(definition)
        if ids is None:
            raise ValidationError(
                gettext_lazy(
                    "Lifecycle state rules require a 'graphid' and a "
                    "'lifecycle_state_id'."
                )
            )
        return ids

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"
