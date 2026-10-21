from dataclasses import dataclass

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
