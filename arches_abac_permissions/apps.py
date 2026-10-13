from django.apps import AppConfig
from django.conf import settings
from django.core.checks import Tags, Warning, register

CORE_TERM_SEARCH = "arches.app.search.search_term.TermSearch"
PERMITTED_TERM_SEARCH = (
    "arches_abac_permissions.permitted_term_search.PermittedTermSearch"
)


class ArchesAbacPermissionsConfig(AppConfig):
    name = "arches_abac_permissions"
    is_arches_application = True

    def ready(self):
        # Register proxy rule models so they are known to the app registry.
        from arches_abac_permissions.rules import (  # noqa
            lifecycle_state_rule,
            queryset_rule,
            search_rule,
        )


@register(Tags.security)
def check_term_search(app_configs, **kwargs):
    modules = [term_search.get("module") for term_search in settings.TERM_SEARCH_TYPES]
    if CORE_TERM_SEARCH not in modules:
        return []
    return [
        Warning(
            "Search suggestions can show values from resources a user can't see",
            hint=f"In TERM_SEARCH_TYPES, replace {CORE_TERM_SEARCH} with {PERMITTED_TERM_SEARCH}.",
            id="arches_abac_permissions.W001",
        )
    ]
