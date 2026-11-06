from django.apps import AppConfig
from django.core.signals import request_finished, request_started


class ArchesAbacPermissionsConfig(AppConfig):
    name = "arches_abac_permissions"
    is_arches_application = True

    def ready(self):
        # Register proxy rule models so they are known to the app registry.
        from arches_abac_permissions.rules import (  # noqa
            lifecycle_state_rule,
            queryset_rule,
            resource_set_rule,
            search_rule,
            spatial_rule,
            tile_node_value_rule,
        )

        from arches_abac_permissions.permissions import (
            arches_abac_permission_framework as framework,
        )

        request_started.connect(
            framework.start_request_reporting,
            dispatch_uid="abac_start_request_reporting",
        )
        request_finished.connect(
            framework.end_request_reporting,
            dispatch_uid="abac_end_request_reporting",
        )
