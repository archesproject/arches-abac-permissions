from django.urls import path

from arches_abac_permissions.views import (
    GroupsView,
    GroupView,
    ResourceModelsView,
    ResourceSetsView,
    RulesView,
    RuleTypesView,
    RuleView,
)

urlpatterns = [
    path("api/abac/rules", RulesView.as_view(), name="abac_rules"),
    path("api/abac/rules/<uuid:rule_id>", RuleView.as_view(), name="abac_rule"),
    path("api/abac/rule_types", RuleTypesView.as_view(), name="abac_rule_types"),
    path(
        "api/abac/resource_models",
        ResourceModelsView.as_view(),
        name="abac_resource_models",
    ),
    path(
        "api/abac/resource_sets", ResourceSetsView.as_view(), name="abac_resource_sets"
    ),
    path("api/abac/groups", GroupsView.as_view(), name="abac_groups"),
    path("api/abac/groups/<int:group_id>", GroupView.as_view(), name="abac_group"),
]
