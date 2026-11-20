import uuid
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from arches.app.models.models import (
    Language,
    Node,
    ResourceInstance,
    TileModel,
)
from arches_abac_permissions.models import InclusionRule
from arches_abac_permissions.rule_types import RuleType
from arches_abac_permissions.rules.utils import get_resource_node

CONTROLLED_LISTS_INSTALLED = apps.is_installed("arches.extensions.controlled_lists")
if CONTROLLED_LISTS_INSTALLED:
    from arches.extensions.controlled_lists.models import ListItem

SUPPORTED_DATATYPES = (
    "string",
    "non-localized-string",
    "number",
    "boolean",
    "date",
    "domain-value",
    "domain-value-list",
    "resource-instance",
    "resource-instance-list",
    "reference",
)
UUID_DATATYPES = ("resource-instance", "resource-instance-list", "reference")


def get_supported_datatypes():
    if CONTROLLED_LISTS_INSTALLED:
        return SUPPORTED_DATATYPES
    return tuple(dt for dt in SUPPORTED_DATATYPES if dt != "reference")


def parse_uuid(value):
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise ValidationError(_("%s is not a valid id.") % value)


class TileArgs(NamedTuple):
    graph_id: uuid.UUID
    node_id: uuid.UUID
    nodegroup_id: uuid.UUID
    datatype: str
    value: str
    language: str


class TileNodeValueRule(InclusionRule):
    """
    Rule matching resources with a tile whose node holds a value.

    definition: {
        "graphid": "<graph id>",
        "nodeid": "<node id>",
        "value": "<value, always a string>",
        "language": "<language code, string nodes only; empty for any>",
        "nodegroupid": "<node's nodegroup id>",
        "datatype": "<node's datatype>"
    }

    nodegroupid and datatype are derived from the node when the rule is
    validated (never taken from clients), so evaluation needs no node lookup.
    Matching only reads the stored values. If the node later moves to another
    nodegroup or changes datatype (e.g. after graph changes), the rule matches
    nothing until it is edited and saved again.

    Matching is exact. List-valued nodes (domain-value-list,
    resource-instance(-list), reference) match when they contain the value.
    Evaluated against the tiles table, so arches-search isn't required.
    """

    rule_type = RuleType(
        key="tile_node_value",
        label=gettext_lazy("Resource has Node Value"),
        description=gettext_lazy(
            "Matches resources with a tile whose node holds a value. "
            "Re-save the rule after changing the node's graph."
        ),
        icon="pi pi-tag",
        definition_keys=("graphid", "nodeid", "value", "language"),
    )

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        return False

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        args = cls.read_args(inclusion_rule.definition)
        tiles = args and cls.get_tiles(args)
        if tiles is None:
            return ResourceInstance.objects.none()
        return ResourceInstance.objects.filter(
            pk__in=tiles.filter(resourceinstance__graph_id=args.graph_id).values(
                "resourceinstance_id"
            )
        )

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        args = cls.read_args(inclusion_rule.definition)
        if args is None or resource.graph_id != args.graph_id:
            return False
        tiles = cls.get_tiles(args)
        return tiles is not None and tiles.filter(resourceinstance=resource).exists()

    @classmethod
    def validate_definition(cls, inclusion_rule):
        """Validate the rule and store its normalized and server-derived values."""
        definition = inclusion_rule.definition
        graphid, nodeid, _value = cls.require_keys(definition)
        node = get_resource_node(graphid, nodeid)
        definition["nodegroupid"] = str(node.nodegroup_id)
        definition["datatype"] = node.datatype
        args = cls.get_args(definition)
        cls.validate_value(node, args.value, args.language)
        definition.update(
            graphid=str(args.graph_id), nodeid=str(args.node_id), value=args.value
        )
        if "language" in definition:
            definition["language"] = args.language

    @classmethod
    def get_index_sql(cls, inclusion_rule):
        # Only the node is needed, so skip the full definition check.
        try:
            node = Node.objects.only("pk", "nodegroup_id").get(
                pk=inclusion_rule.definition.get("nodeid")
            )
        except (Node.DoesNotExist, ValidationError):
            return None
        # Ids come from the database, so formatting them into SQL is safe.
        return (
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS abac_tile_node_{node.pk.hex}\n"
            f"    ON tiles USING gin ((tiledata -> '{node.pk}') jsonb_path_ops)\n"
            f"    WHERE nodegroupid = '{node.nodegroup_id}';"
        )

    @staticmethod
    def read_args(definition):
        """
        Read the values validate_definition stored, without validating them.
        None if they're missing or malformed, so the rule matches nothing.
        """
        try:
            return TileArgs(
                uuid.UUID(str(definition["graphid"])),
                uuid.UUID(str(definition["nodeid"])),
                uuid.UUID(str(definition["nodegroupid"])),
                definition["datatype"],
                definition["value"],
                definition.get("language") or "",
            )
        except (KeyError, ValueError, TypeError):
            return None

    @classmethod
    def get_tiles(cls, args):
        """Return the tiles whose node holds the value, or None if it's malformed."""
        lookup = f"data__{args.node_id}__contains"
        value_filter = Q()
        try:
            for fragment in cls.get_fragments(args):
                value_filter |= Q(**{lookup: fragment})
        except (KeyError, ValueError, TypeError):
            return None
        if not value_filter:
            # A string rule for "any language" with no languages matches nothing.
            value_filter = Q(pk__in=[])
        return TileModel.objects.filter(value_filter, nodegroup_id=args.nodegroup_id)

    @staticmethod
    def get_fragments(args):
        """JSON fragments; a tile matches if its node value contains any of them."""
        value = args.value
        match args.datatype:
            case "string":
                codes = (
                    [args.language]
                    if args.language
                    else Language.objects.values_list("code", flat=True)
                )
                return [{code: {"value": value}} for code in codes]
            case "number":
                # Stored in canonical form: an integer, or a float.
                try:
                    return [int(value)]
                except ValueError:
                    return [float(value)]
            case "boolean":
                return [{"true": True, "false": False}[value]]
            case "domain-value-list":
                return [[value]]
            case "resource-instance" | "resource-instance-list":
                return [[{"resourceId": value}]]
            case "reference":
                return [[{"labels": [{"list_item_id": value}]}]]
            case "non-localized-string" | "date" | "domain-value":
                return [value]
            case _:
                raise ValueError(args.datatype)

    @staticmethod
    def require_keys(definition):
        graphid = definition.get("graphid")
        nodeid = definition.get("nodeid")
        value = definition.get("value")
        if not graphid or not nodeid or value in (None, ""):
            raise ValidationError(
                _(
                    "Tile node value rules require a 'graphid', a 'nodeid' and a 'value'."
                )
            )
        return graphid, nodeid, value

    @classmethod
    def get_args(cls, definition):
        """Validate the definition without database access; return its parsed values."""
        graphid, nodeid, value = cls.require_keys(definition)
        datatype = definition.get("datatype")
        value = str(value)
        language = definition.get("language") or ""
        if datatype not in get_supported_datatypes():
            raise ValidationError(
                _("Nodes of datatype %s are not supported.") % datatype
            )
        if language and datatype != "string":
            raise ValidationError(_("Only string nodes take a language."))
        if datatype in UUID_DATATYPES:
            value = str(parse_uuid(value))
        elif datatype == "number":
            try:
                number = Decimal(value)
                if not number.is_finite():
                    raise InvalidOperation
            except InvalidOperation:
                raise ValidationError(_("%s is not a number.") % value)
            if number == number.to_integral():
                value = str(int(number))
            else:
                # Non-integers are matched as floats; reject any that would round.
                if Decimal(repr(float(number))) != number:
                    raise ValidationError(
                        _("%s has more precision than can be matched.") % value
                    )
                value = repr(float(number))
        elif datatype == "boolean" and value not in ("true", "false"):
            raise ValidationError(_("A boolean value must be 'true' or 'false'."))
        return TileArgs(
            parse_uuid(graphid),
            parse_uuid(nodeid),
            parse_uuid(definition.get("nodegroupid")),
            datatype,
            value,
            language,
        )

    @staticmethod
    def validate_value(node, value, language):
        """Checks that need the database; run when a rule is saved."""
        match node.datatype:
            case "string":
                if language and not Language.objects.filter(code=language).exists():
                    raise ValidationError(_("%s is not a language.") % language)
            case "domain-value" | "domain-value-list":
                options = (node.config or {}).get("options") or []
                if value not in {str(option.get("id")) for option in options}:
                    raise ValidationError(
                        _("%s is not an option of this node.") % value
                    )
            case "resource-instance" | "resource-instance-list":
                if not ResourceInstance.objects.filter(pk=value).exists():
                    raise ValidationError(_("%s is not the id of a resource.") % value)
            case "reference":
                list_id = (node.config or {}).get("controlledList")
                if not ListItem.objects.filter(pk=value, list_id=list_id).exists():
                    raise ValidationError(
                        _("%s is not an item of this node's controlled list.") % value
                    )

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"
