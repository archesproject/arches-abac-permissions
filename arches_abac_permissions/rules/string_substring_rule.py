import json

from django.core.exceptions import ValidationError
from django.db.models import BooleanField, Exists, F, Func, OuterRef, Value

from arches.app.models.models import Node, ResourceInstance, TileModel
from arches_abac_permissions.models import InclusionRule


class JsonbPathExists(Func):
    function = "jsonb_path_exists"
    template = "%(function)s(%(expressions)s::jsonpath)"
    output_field = BooleanField()


def localized_substring_path(nodeid, substring):
    # Matches when the value in any language contains the substring. The "q"
    # flag treats the pattern literally and "i" makes it case-insensitive. In
    # lax mode, a null or non-object node value simply yields no match.
    return (
        f"$.{json.dumps(nodeid)}.*.value"
        f' ? (@ like_regex {json.dumps(substring)} flag "iq")'
    )


class StringSubstringRule(InclusionRule):
    """
    Rule matching resources whose string node value contains a substring.

    definition: {"nodeid": "<string node id>", "substring": "<text>"}

    Matching is case-insensitive and checks the value in every language.
    """

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        # Arches search has no equivalent: its string "like" operator either
        # prefix-matches each word or, for quoted terms, matches case-sensitively
        # within a single language.
        return False

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        node, substring = cls.parse_definition(inclusion_rule.definition)
        path = localized_substring_path(str(node.pk), substring)
        matching_tiles = TileModel.objects.filter(
            JsonbPathExists(F("data"), Value(path)),
            resourceinstance=OuterRef("pk"),
            nodegroup_id=node.nodegroup_id,
        )
        return ResourceInstance.objects.filter(Exists(matching_tiles))

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        return (
            cls.get_matching_resources(inclusion_rule)
            .filter(pk=resource.pk)
            .exists()
        )

    @staticmethod
    def parse_definition(definition):
        nodeid = definition.get("nodeid")
        substring = definition.get("substring")
        if not nodeid or not substring:
            raise ValidationError(
                "String substring rules require a 'nodeid' and a non-empty 'substring'."
            )
        try:
            node = Node.objects.get(pk=nodeid, datatype="string")
        except (Node.DoesNotExist, ValidationError):
            raise ValidationError(f"{nodeid} is not the id of a string node.")
        return node, substring

    class Meta:
        proxy = True
        app_label = "arches_abac_permissions"
