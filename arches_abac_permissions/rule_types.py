from dataclasses import dataclass

from django.apps import apps
from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class RuleType:
    key: str
    modulename: str
    classname: str
    label: str
    description: str
    icon: str
    definition_keys: tuple[str, ...]
    required_app: str | None = None

    @property
    def available(self):
        return self.required_app is None or apps.is_installed(self.required_app)


# Types the rule-permissions UI can create and edit. Clients send only the
# key; the module and class are always resolved here.
RULE_TYPES = {
    "lifecycle_state": RuleType(
        key="lifecycle_state",
        modulename="lifecycle_state_rule.py",
        classname="LifecycleStateRule",
        label=_("Resource has Lifecycle State"),
        description=_(
            "Matches resources of a resource model that are in a lifecycle state"
        ),
        icon="pi pi-sync",
        definition_keys=("graphid", "lifecycle_state_id"),
    ),
    "resource_set": RuleType(
        key="resource_set",
        modulename="resource_set_rule.py",
        classname="ResourceSetRule",
        label=_("Resource is in Resource Set"),
        description=_("Matches the members of a resource set"),
        icon="pi pi-th-large",
        definition_keys=("resource_set_id",),
        required_app="arches_resource_sets",
    ),
    "tile_node_value": RuleType(
        key="tile_node_value",
        modulename="tile_node_value_rule.py",
        classname="TileNodeValueRule",
        label=_("Resource has Node Value"),
        description=_("Matches resources with a tile whose node holds a value"),
        icon="pi pi-tag",
        definition_keys=("graphid", "nodeid", "value", "language"),
    ),
}

# UI permission name -> resource instance permission codename.
PERMISSION_CODENAMES = {
    "read": "view_resourceinstance",
    "update": "change_resourceinstance",
    "delete": "delete_resourceinstance",
}


def get_rule_type_for_classname(classname):
    for rule_type in RULE_TYPES.values():
        if rule_type.classname == classname:
            return rule_type
    return None
