from django.contrib import admin
from django.db import transaction

from arches_abac_permissions.models import InclusionRule, InclusionRuleGroupPermission
from arches_abac_permissions.reindex import reindex_resources, rule_matches

RULE_FIELDS = {"modulename", "classname", "definition"}


def granted_rule_matches(rule):
    # A rule with no grants adds no groups to the index.
    return rule_matches(rule) if rule.group_permissions.exists() else set()


class InclusionRuleGroupPermissionInline(admin.StackedInline):
    model = InclusionRuleGroupPermission
    extra = 0
    filter_horizontal = ["permissions"]


@admin.register(InclusionRule)
class InclusionRuleAdmin(admin.ModelAdmin):
    list_display = ["name", "classname", "owner", "created"]
    list_filter = ["classname"]
    search_fields = ["name"]
    readonly_fields = ["inclusionruleid", "created"]
    inlines = [InclusionRuleGroupPermissionInline]

    def save_model(self, request, obj, form, change):
        previous = InclusionRule.objects.filter(pk=obj.pk).first() if change else None
        request.abac_previous_matches = (
            granted_rule_matches(previous) if previous else set()
        )
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if RULE_FIELDS & set(form.changed_data) or any(
            formset.has_changed() for formset in formsets
        ):
            ids = request.abac_previous_matches | granted_rule_matches(form.instance)
            transaction.on_commit(lambda: reindex_resources(ids))

    def delete_model(self, request, obj):
        ids = granted_rule_matches(obj)
        super().delete_model(request, obj)
        transaction.on_commit(lambda: reindex_resources(ids))

    def delete_queryset(self, request, queryset):
        ids = set().union(*(granted_rule_matches(rule) for rule in queryset))
        super().delete_queryset(request, queryset)
        transaction.on_commit(lambda: reindex_resources(ids))
