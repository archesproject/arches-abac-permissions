from django.contrib import admin

from arches_abac_permissions.models import InclusionRule, InclusionRuleGroupPermission


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
