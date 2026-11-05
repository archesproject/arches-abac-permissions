from dataclasses import dataclass, field, replace

from django.apps import apps


@dataclass(frozen=True)
class RuleType:
    """
    UI metadata a rule class declares as its `rule_type` attribute to make
    it creatable from the rule-permissions plugin.
    """

    key: str
    label: str
    description: str
    icon: str
    definition_keys: tuple[str, ...]
    required_app: str | None = None
    modulename: str = field(default="", compare=False)
    classname: str = field(default="", compare=False)

    @property
    def available(self):
        return self.required_app is None or apps.is_installed(self.required_app)


def _rule_classes(base):
    for subclass in base.__subclasses__():
        yield subclass
        yield from _rule_classes(subclass)


def get_rule_types():
    """
    Rule types keyed by `RuleType.key`. Clients send only the key; module and
    class names are always resolved here from the declaring rule class.
    """
    from arches_abac_permissions.models import InclusionRule

    rule_types = {}
    for rule_class in _rule_classes(InclusionRule):
        rule_type = rule_class.__dict__.get("rule_type")
        if isinstance(rule_type, RuleType):
            rule_types[rule_type.key] = replace(
                rule_type,
                modulename=f"{rule_class.__module__.rsplit('.', 1)[-1]}.py",
                classname=rule_class.__name__,
            )
    return rule_types


def get_rule_type_for_rule(modulename, classname):
    for rule_type in get_rule_types().values():
        if (rule_type.modulename, rule_type.classname) == (modulename, classname):
            return rule_type
    return None


# Groups created by Arches core migrations; Arches looks some up by name.
BUILT_IN_GROUP_NAMES = frozenset(
    {
        "Application Administrator",
        "Crowdsource Editor",
        "Graph Editor",
        "Guest",
        "Mobile Project Administrator",
        "RDM Administrator",
        "Resource Editor",
        "Resource Exporter",
        "Resource Reviewer",
        "System Administrator",
    }
)

# Logged-out visitors are this user (SetAnonymousUser), and it belongs to Guest.
ANONYMOUS_USERNAME = "anonymous"
PUBLIC_GROUP_NAME = "Guest"

# UI permission name -> resource instance permission codename.
PERMISSION_CODENAMES = {
    "read": "view_resourceinstance",
    "update": "change_resourceinstance",
    "delete": "delete_resourceinstance",
}
