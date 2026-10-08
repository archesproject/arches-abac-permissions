from arches.app.models.models import ResourceInstance
from arches_abac_permissions.models import InclusionRule


class QuerySetRule(InclusionRule):
    """Rule whose definition describes a queryset filter."""

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        # TODO: queryset rules have no search url equivalent yet.
        return False

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        # TODO: queryset rules are not evaluated yet.
        return ResourceInstance.objects.none()

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        # TODO: queryset rules are not evaluated yet.
        return False

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"
