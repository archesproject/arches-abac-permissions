from django.urls import path

from arches_abac_permissions.membership_views import (
    UserGroupMembershipView,
    UsersView,
)
from arches_abac_permissions.views import (
    ControlledListItemsView,
    GroupsView,
    GroupView,
    LanguagesView,
    MapConfigView,
    ResourceModelNodesView,
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
        "api/abac/resource_models/<uuid:graph_id>/nodes",
        ResourceModelNodesView.as_view(),
        name="abac_resource_model_nodes",
    ),
    path("api/abac/languages", LanguagesView.as_view(), name="abac_languages"),
    path("api/abac/map_config", MapConfigView.as_view(), name="abac_map_config"),
    path(
        "api/abac/controlled_lists/<uuid:list_id>/items",
        ControlledListItemsView.as_view(),
        name="abac_controlled_list_items",
    ),
    path(
        "api/abac/resource_sets", ResourceSetsView.as_view(), name="abac_resource_sets"
    ),
    path("api/abac/groups", GroupsView.as_view(), name="abac_groups"),
    path("api/abac/groups/<int:group_id>", GroupView.as_view(), name="abac_group"),
    path("api/abac/users", UsersView.as_view(), name="abac_users"),
    path(
        "api/abac/users/group_membership",
        UserGroupMembershipView.as_view(),
        name="abac_user_group_membership",
    ),
]
