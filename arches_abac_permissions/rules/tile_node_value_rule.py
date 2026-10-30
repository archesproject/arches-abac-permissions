import uuid
from decimal import Decimal, InvalidOperation

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext as _

from arches.app.models.models import (
    GraphModel,
    Language,
    Node,
    ResourceInstance,
    TileModel,
)
from arches_abac_permissions.models import InclusionRule

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


class TileNodeValueRule(InclusionRule):
    """
    Rule matching resources with a tile whose node holds a value.

    definition: {
        "graphid": "<graph id>",
        "nodeid": "<node id>",
        "value": "<value, always a string>",
        "language": "<language code, string nodes only; empty for any>"
    }

    Matching is exact. List-valued nodes (domain-value-list,
    resource-instance(-list), reference) match when they contain the value.
    Evaluated against the tiles table, so arches-search isn't required.
    """

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        return False

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        node, value_filter = cls.get_tile_filter(inclusion_rule.definition)
        tiles = TileModel.objects.filter(
            value_filter,
            nodegroup_id=node.nodegroup_id,
            resourceinstance__graph_id=node.graph_id,
        )
        return ResourceInstance.objects.filter(
            pk__in=tiles.values("resourceinstance_id")
        )

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        node, value_filter = cls.get_tile_filter(inclusion_rule.definition)
        if resource.graph_id != node.graph_id:
            return False
        return TileModel.objects.filter(
            value_filter, nodegroup_id=node.nodegroup_id, resourceinstance=resource
        ).exists()

    @classmethod
    def validate_definition(cls, inclusion_rule):
        cls.parse_definition(inclusion_rule.definition, validate_value=True)

    @classmethod
    def get_index_sql(cls, inclusion_rule):
        node, _value, _language = cls.parse_definition(inclusion_rule.definition)
        # Ids come from the database, so formatting them into SQL is safe.
        return (
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS abac_tile_node_{node.pk.hex}\n"
            f"    ON tiles USING gin ((tiledata -> '{node.pk}') jsonb_path_ops)\n"
            f"    WHERE nodegroupid = '{node.nodegroup_id}';"
        )

    @classmethod
    def get_tile_filter(cls, definition):
        """Return the node and a Q matching tiles whose node holds the value."""
        node, value, language = cls.parse_definition(definition)
        lookup = f"data__{node.pk}__contains"
        value_filter = Q()
        for fragment in cls.get_fragments(node, value, language):
            value_filter |= Q(**{lookup: fragment})
        if not value_filter:
            # A string rule for "any language" with no languages matches nothing.
            value_filter = Q(pk__in=[])
        return node, value_filter

    @staticmethod
    def get_fragments(node, value, language):
        """JSON fragments; a tile matches if its node value contains any of them."""
        match node.datatype:
            case "string":
                codes = (
                    [language]
                    if language
                    else Language.objects.values_list("code", flat=True)
                )
                return [{code: {"value": value}} for code in codes]
            case "number":
                number = Decimal(value)
                return [
                    int(number) if number == number.to_integral() else float(number)
                ]
            case "boolean":
                return [value == "true"]
            case "domain-value-list":
                return [[value]]
            case "resource-instance" | "resource-instance-list":
                return [[{"resourceId": value}]]
            case "reference":
                return [[{"labels": [{"list_item_id": value}]}]]
            case _:
                return [value]

    @classmethod
    def parse_definition(cls, definition, validate_value=False):
        graphid = definition.get("graphid")
        nodeid = definition.get("nodeid")
        value = definition.get("value")
        language = definition.get("language") or ""
        if not graphid or not nodeid or value in (None, ""):
            raise ValidationError(
                _(
                    "Tile node value rules require a 'graphid', a 'nodeid' and a 'value'."
                )
            )
        try:
            graph = GraphModel.objects.get(pk=graphid, isresource=True)
        except (GraphModel.DoesNotExist, ValidationError):
            raise ValidationError(_("%s is not the id of a resource model.") % graphid)
        try:
            node = Node.objects.get(pk=nodeid, graph=graph)
        except (Node.DoesNotExist, ValidationError):
            raise ValidationError(
                _("%(nodeid)s is not the id of a node of graph %(graphid)s.")
                % {"nodeid": nodeid, "graphid": graphid}
            )
        if node.datatype not in get_supported_datatypes():
            raise ValidationError(
                _("Nodes of datatype %s are not supported.") % node.datatype
            )
        if language and node.datatype != "string":
            raise ValidationError(_("Only string nodes take a language."))
        if node.datatype in UUID_DATATYPES:
            value = str(parse_uuid(value))
        elif node.datatype == "number":
            try:
                if not Decimal(value).is_finite():
                    raise InvalidOperation
            except InvalidOperation:
                raise ValidationError(_("%s is not a number.") % value)
        elif node.datatype == "boolean" and value not in ("true", "false"):
            raise ValidationError(_("A boolean value must be 'true' or 'false'."))
        if validate_value:
            cls.validate_value(node, value, language)
        return node, value, language

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
