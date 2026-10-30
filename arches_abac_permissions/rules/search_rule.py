import json
from urllib.parse import quote, urlencode

from django.urls import reverse

from arches.app.models.models import ResourceInstance
from arches_abac_permissions.models import InclusionRule


class SearchRule(InclusionRule):
    """Rule whose definition is a saved search-url query."""

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        query = urlencode(
            {k: json.dumps(v) for k, v in inclusion_rule.definition.items()},
            quote_via=quote,
        )
        return f"{reverse('search_home')}?{query}"

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        # TODO: search rules are not evaluated yet.
        return ResourceInstance.objects.none()

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        # TODO: search rules are not evaluated yet.
        return False

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"
