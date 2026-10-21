import json
from urllib.parse import quote, urlencode

from django.urls import reverse

from arches_abac_permissions.models import InclusionRule


class SearchRule(InclusionRule):
    """Rule whose definition is a saved search-url query."""

    @classmethod
    def do_get_search_rule_url(cls, inclusion_rule):
        query = urlencode(
            {k: json.dumps(v) for k, v in inclusion_rule.definition.items()},
            quote_via=quote,
        )
        return f"{reverse('search_home')}?{query}"

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"
