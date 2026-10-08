from django.apps import AppConfig


class ArchesAbacPermissionsConfig(AppConfig):
    name = "arches_abac_permissions"
    is_arches_application = True

    def ready(self):
        # Register proxy rule models so they are known to the app registry.
        from arches_abac_permissions.rules import (  # noqa
            queryset_rule,
            search_rule,
            string_substring_rule,
        )
