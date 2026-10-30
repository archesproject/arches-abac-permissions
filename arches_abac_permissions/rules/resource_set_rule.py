from django.apps import apps
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from arches.app.models.models import ResourceInstance
from arches_abac_permissions.models import InclusionRule

# arches-resource-sets is optional, and this module is imported at startup by apps.py.
RESOURCE_SETS_INSTALLED = apps.is_installed("arches_resource_sets")
if RESOURCE_SETS_INSTALLED:
    from arches_resource_sets.models import ResourceSet, ResourceSetMember


class ResourceSetRule(InclusionRule):
    """
    Rule matching the members of an arches-resource-sets resource set.

    definition: {"resource_set_id": "<resource set id>"}
    """

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        return False

    @classmethod
    def get_index_sql(cls, inclusion_rule):
        # resource_set_member's unique (resource_set_id, resource_instance_id)
        # constraint already indexes membership lookups.
        return None

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        set_id = cls.parse_definition(inclusion_rule.definition)
        members = ResourceSetMember.objects.filter(resource_set_id=set_id)
        return ResourceInstance.objects.filter(
            pk__in=members.values("resource_instance_id")
        )

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        set_id = cls.parse_definition(inclusion_rule.definition)
        return ResourceSetMember.objects.filter(
            resource_set_id=set_id, resource_instance_id=resource.pk
        ).exists()

    @classmethod
    def validate_definition(cls, inclusion_rule):
        set_id = cls.parse_definition(inclusion_rule.definition)
        try:
            ResourceSet.objects.get(pk=set_id)
        except (ResourceSet.DoesNotExist, ValidationError):
            raise ValidationError(_("%s is not the id of a resource set.") % set_id)

    @staticmethod
    def parse_definition(definition):
        if not RESOURCE_SETS_INSTALLED:
            raise ValidationError(_("Resource set rules require arches-resource-sets."))
        set_id = definition.get("resource_set_id")
        if not set_id:
            raise ValidationError(_("Resource set rules require a 'resource_set_id'."))
        return set_id

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"
