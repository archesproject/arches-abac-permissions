import json
from urllib.parse import quote, urlencode

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import gettext as _
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
        graph, state = cls.parse_definition(inclusion_rule.definition)
        filters = {
            "resource-type-filter": [{"graphid": str(graph.pk), "inverted": False}],
            "lifecycle-state-filter": [{"id": str(state.pk), "inverted": False}],
        }
        query = urlencode(
            {k: json.dumps(v) for k, v in filters.items()}, quote_via=quote
        )
        return f"{reverse('search_home')}?{query}"

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        graph, state = cls.parse_definition(inclusion_rule.definition)
        return ResourceInstance.objects.filter(
            graph=graph, resource_instance_lifecycle_state=state
        )

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        graph, state = cls.parse_definition(inclusion_rule.definition)
        return (
            resource.graph_id == graph.pk
            and resource.resource_instance_lifecycle_state_id == state.pk
        )

    @classmethod
    def validate_definition(cls, inclusion_rule):
        cls.parse_definition(inclusion_rule.definition)

    @classmethod
    def get_index_sql(cls, inclusion_rule):
        # One index serves every lifecycle state rule.
        return (
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS abac_resource_graph_lifecycle_state\n"
            "    ON resource_instances (graphid, resource_instance_lifecycle_state_id);"
        )

    @staticmethod
    def parse_definition(definition):
        graphid = definition.get("graphid")
        stateid = definition.get("lifecycle_state_id")
        if not graphid or not stateid:
            raise ValidationError(
                _(
                    "Lifecycle state rules require a 'graphid' and a 'lifecycle_state_id'."
                )
            )
        try:
            graph = GraphModel.objects.get(pk=graphid, isresource=True)
        except (GraphModel.DoesNotExist, ValidationError):
            raise ValidationError(_("%s is not the id of a resource model.") % graphid)
        try:
            state = ResourceInstanceLifecycleState.objects.get(
                pk=stateid,
                resource_instance_lifecycle_id=graph.resource_instance_lifecycle_id,
            )
        except (ResourceInstanceLifecycleState.DoesNotExist, ValidationError):
            raise ValidationError(
                _(
                    "%(stateid)s is not the id of a lifecycle state of graph %(graphid)s."
                )
                % {"stateid": stateid, "graphid": graphid}
            )
        return graph, state

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"
