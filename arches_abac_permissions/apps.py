from django.apps import AppConfig


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
        from celery.signals import task_postrun, task_prerun
        from django.core.signals import request_finished, request_started

        from arches_abac_permissions.rule_cache import clear_cache, start_cache

        for signal, handler in (
            (request_started, start_cache),
            (task_prerun, start_cache),
            (request_finished, clear_cache),
            (task_postrun, clear_cache),
        ):
            signal.connect(handler, dispatch_uid=f"abac_{handler.__name__}")
