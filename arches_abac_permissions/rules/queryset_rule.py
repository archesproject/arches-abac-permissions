from arches_abac_permissions.models import InclusionRule


class QuerySetRule(InclusionRule):
    """Rule whose definition describes a queryset filter."""

    @classmethod
    def do_get_search_rule_url(cls, inclusion_rule):
        # TODO: queryset rules have no search url equivalent yet.
        return False

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"
