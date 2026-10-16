from django.apps import apps
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils import translation
from django.utils.translation import gettext as _

from arches_abac_permissions.models import InclusionRule

CURRENT_USER_OPERATORS = {"IS_CURRENT_USER", "IS_NOT_CURRENT_USER"}

# arches-search is optional, and this module is imported at startup by apps.py.
ARCHES_SEARCH_INSTALLED = apps.is_installed("arches_search")
if ARCHES_SEARCH_INSTALLED:
    from arches_search.utils.advanced_search.advanced_search import (
        AdvancedSearchQueryCompiler,
    )


def _values(node, key):
    """Every value stored under key, at any depth of a JSON payload."""
    found = []
    if isinstance(node, dict):
        for node_key, value in node.items():
            if node_key == key:
                found.append(value)
            found += _values(value, key)
    elif isinstance(node, list):
        for item in node:
            found += _values(item, key)
    return found


class SearchRule(InclusionRule):
    """
    Rule matching the resources an arches-search advanced search query matches.

    definition: {"advanced_search_query": <one graph's arches-search query>}
    """

    @classmethod
    def compile(cls, inclusion_rule):
        """The lazy queryset the rule's query matches. Raises ValidationError if invalid."""
        definition = inclusion_rule.definition
        if (
            not isinstance(definition, dict)
            or definition.keys() != {"advanced_search_query"}
            or not isinstance(definition["advanced_search_query"], dict)
        ):
            raise ValidationError(
                _(
                    'A search rule\'s definition must be {"advanced_search_query": {...}}.'
                )
            )
        query = definition["advanced_search_query"]
        # An AND query with no clauses compiles to no filter, matching the whole graph.
        if not any(_values(query, "clauses")):
            raise ValidationError(
                _("A search rule's query must have at least one clause.")
            )
        # With no user, arches-search treats "is not me" as unconstrained, so a rule
        # using it would match every resource of the graph.
        if CURRENT_USER_OPERATORS.intersection(_values(query, "operator")):
            raise ValidationError(
                _(
                    "Search rules can't use 'is me' or 'is not me': a rule doesn't "
                    "run as any one user."
                )
            )
        if not ARCHES_SEARCH_INSTALLED:
            raise ValidationError(_("Search rules require arches-search."))

        try:
            # user=None is arches-search's trusted caller: every node is readable
            # and no permissions are applied.
            with translation.override(settings.LANGUAGE_CODE):
                return AdvancedSearchQueryCompiler(query, user=None).compile()
        except (ValueError, NotImplementedError, ObjectDoesNotExist) as error:
            raise ValidationError(str(error))

    @classmethod
    def validate_definition(cls, inclusion_rule):
        cls.compile(inclusion_rule)

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        return cls.compile(inclusion_rule)

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        return cls.compile(inclusion_rule).filter(pk=resource.pk).exists()

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        return False

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"
