import uuid

from django.contrib.auth.models import Group, Permission, User
from django.db import models
from django.db.models import deletion

from arches.app.utils.module_importer import get_class_from_modulename
from arches_abac_permissions.const import RuleExtensionType


class InclusionRule(models.Model):
    inclusionruleid = models.UUIDField(
        default=uuid.uuid4, primary_key=True, serialize=False
    )
    owner = models.ForeignKey(
        User, db_column="owner_id", on_delete=deletion.SET_NULL, null=True
    )
    name = models.TextField()
    modulename = models.TextField(blank=True, null=True)
    classname = models.TextField(blank=True, null=True)
    definition = models.JSONField()
    created = models.DateTimeField(auto_now_add=True)

    def get_class_module(self):
        return get_class_from_modulename(
            self.modulename, self.classname, RuleExtensionType.RULES
        )

    def get_search_rule_url(self):
        return self.get_class_module().do_get_search_rule_url(self)

    def __str__(self):
        return self.name

    class Meta:
        managed = True
        db_table = "inclusion_rules"
        app_label = "arches_abac_permissions"


class InclusionRuleGroupPermission(models.Model):
    """Group `group` gets `permissions` on all resources matching `rule`."""

    rule = models.ForeignKey(
        InclusionRule, on_delete=models.CASCADE, related_name="group_permissions"
    )
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="inclusion_rule_permissions"
    )
    permissions = models.ManyToManyField(
        Permission, blank=True, related_name="inclusion_rule_group_permissions"
    )

    class Meta:
        managed = True
        db_table = "inclusion_rule_group_permissions"
        app_label = "arches_abac_permissions"
        constraints = [
            models.UniqueConstraint(
                fields=["rule", "group"], name="unique_inclusion_rule_group"
            )
        ]
