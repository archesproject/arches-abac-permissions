import json
from http import HTTPStatus

from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils.translation import gettext as _

from arches.app.models.models import GraphModel, Language, Node
from arches.app.models.system_settings import settings
from arches.app.utils.i18n import get_localized_value
from arches.app.utils.response import JSONErrorResponse, JSONResponse
from arches.app.views.api import APIBase
from arches_abac_permissions.models import InclusionRule, InclusionRuleGroupPermission
from arches_abac_permissions.rule_types import (
    PERMISSION_CODENAMES,
    RULE_TYPES,
    get_rule_type_for_classname,
)
from arches_abac_permissions.rules.tile_node_value_rule import get_supported_datatypes

GROUP_NAME_MAX_LENGTH = 150
CODENAME_TO_PERMISSION = {value: key for key, value in PERMISSION_CODENAMES.items()}


class BadRequest(Exception):
    pass


class SuperuserAPIView(APIBase):
    """Every endpoint is restricted to superusers."""

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_superuser):
            return JSONErrorResponse(
                message=_("Only superusers can manage rule permissions."),
                status=HTTPStatus.FORBIDDEN,
            )
        try:
            return super().dispatch(request, *args, **kwargs)
        except BadRequest as e:
            return JSONErrorResponse(message=str(e), status=HTTPStatus.BAD_REQUEST)

    @staticmethod
    def get_json_body(request):
        try:
            body = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            raise BadRequest(_("Request body must be valid JSON."))
        if not isinstance(body, dict):
            raise BadRequest(_("Request body must be a JSON object."))
        return body


def serialize_rule(rule):
    rule_type = get_rule_type_for_classname(rule.classname)
    group_permissions = []
    for grant in rule.group_permissions.all():
        codenames = {permission.codename for permission in grant.permissions.all()}
        group_permissions.append(
            {
                "groupid": grant.group_id,
                "permissions": [
                    name
                    for name, codename in PERMISSION_CODENAMES.items()
                    if codename in codenames
                ],
            }
        )
    group_permissions.sort(key=lambda grant: grant["groupid"])
    try:
        index_sql = rule.get_index_sql_for_rule()
    except (ValidationError, ImportError, AttributeError):
        index_sql = None
    return {
        "id": str(rule.pk),
        "name": rule.name,
        "description": rule.description,
        "active": rule.active,
        "rule_type": rule_type.key if rule_type else None,
        "definition": rule.definition,
        "group_permissions": group_permissions,
        "index_sql": index_sql,
    }


def get_rules_queryset():
    classnames = [rule_type.classname for rule_type in RULE_TYPES.values()]
    return InclusionRule.objects.filter(classname__in=classnames).prefetch_related(
        "group_permissions__permissions"
    )


def parse_rule_payload(body):
    """Validate a rule payload and return field values, definition, and grants."""
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise BadRequest(_("A rule name is required."))
    description = body.get("description", "")
    if not isinstance(description, str):
        raise BadRequest(_("The description must be text."))
    active = body.get("active", True)
    if not isinstance(active, bool):
        raise BadRequest(_("'active' must be true or false."))

    rule_type = RULE_TYPES.get(body.get("rule_type"))
    if rule_type is None or not rule_type.available:
        raise BadRequest(_("Unknown rule type."))

    raw_definition = body.get("definition")
    if not isinstance(raw_definition, dict):
        raise BadRequest(_("A rule definition is required."))
    definition = {
        key: str(raw_definition[key])
        for key in rule_type.definition_keys
        if raw_definition.get(key) is not None
    }
    rule = InclusionRule(
        modulename=rule_type.modulename,
        classname=rule_type.classname,
        definition=definition,
    )
    try:
        rule.get_class_module().validate_definition(rule)
    except ValidationError as e:
        raise BadRequest(" ".join(e.messages))

    grants = {}
    group_permissions = body.get("group_permissions", [])
    if not isinstance(group_permissions, list):
        raise BadRequest(_("'group_permissions' must be a list."))
    for item in group_permissions:
        if not isinstance(item, dict):
            raise BadRequest(_("Invalid group permission."))
        groupid = item.get("groupid")
        permissions = item.get("permissions", [])
        if isinstance(groupid, bool) or not isinstance(groupid, int):
            raise BadRequest(_("Invalid group id."))
        if not isinstance(permissions, list) or any(
            permission not in PERMISSION_CODENAMES for permission in permissions
        ):
            raise BadRequest(_("Invalid permission."))
        grants[groupid] = set(permissions)

    existing = set(Group.objects.filter(pk__in=grants).values_list("pk", flat=True))
    if existing != set(grants):
        raise BadRequest(_("Unknown group."))

    return (
        {
            "name": name.strip(),
            "description": description,
            "active": active,
            "modulename": rule_type.modulename,
            "classname": rule_type.classname,
            "definition": definition,
        },
        grants,
    )


def replace_grants(rule, grants):
    permissions = {
        permission.codename: permission
        for permission in Permission.objects.filter(
            content_type__app_label="models",
            codename__in=PERMISSION_CODENAMES.values(),
        )
    }
    rule.group_permissions.exclude(group_id__in=grants).delete()
    for groupid, names in grants.items():
        if not names:
            rule.group_permissions.filter(group_id=groupid).delete()
            continue
        grant, _created = InclusionRuleGroupPermission.objects.get_or_create(
            rule=rule, group_id=groupid
        )
        grant.permissions.set(permissions[PERMISSION_CODENAMES[name]] for name in names)


class RulesView(SuperuserAPIView):
    def get(self, request):
        rules = get_rules_queryset().order_by("name", "created")
        return JSONResponse({"rules": [serialize_rule(rule) for rule in rules]})

    def post(self, request):
        fields, grants = parse_rule_payload(self.get_json_body(request))
        with transaction.atomic():
            rule = InclusionRule.objects.create(owner=request.user, **fields)
            replace_grants(rule, grants)
        rule = get_rules_queryset().get(pk=rule.pk)
        return JSONResponse(serialize_rule(rule), status=HTTPStatus.CREATED)


class RuleView(SuperuserAPIView):
    def get(self, request, rule_id):
        try:
            rule = get_rules_queryset().get(pk=rule_id)
        except InclusionRule.DoesNotExist:
            return self.not_found()
        return JSONResponse(serialize_rule(rule))

    def put(self, request, rule_id):
        fields, grants = parse_rule_payload(self.get_json_body(request))
        with transaction.atomic():
            try:
                rule = get_rules_queryset().select_for_update().get(pk=rule_id)
            except InclusionRule.DoesNotExist:
                return self.not_found()
            for field, value in fields.items():
                setattr(rule, field, value)
            rule.save()
            replace_grants(rule, grants)
        rule = get_rules_queryset().get(pk=rule_id)
        return JSONResponse(serialize_rule(rule))

    def delete(self, request, rule_id):
        deleted, _details = get_rules_queryset().filter(pk=rule_id).delete()
        if not deleted:
            return self.not_found()
        return HttpResponse(status=HTTPStatus.NO_CONTENT)

    @staticmethod
    def not_found():
        return JSONErrorResponse(
            message=_("Rule not found."), status=HTTPStatus.NOT_FOUND
        )


class RuleTypesView(SuperuserAPIView):
    def get(self, request):
        return JSONResponse(
            {
                "rule_types": [
                    {
                        "key": rule_type.key,
                        "label": str(rule_type.label),
                        "description": str(rule_type.description),
                        "icon": rule_type.icon,
                    }
                    for rule_type in RULE_TYPES.values()
                    if rule_type.available
                ]
            }
        )


class ResourceModelsView(SuperuserAPIView):
    def get(self, request):
        graphs = (
            GraphModel.objects.filter(isresource=True, source_identifier=None)
            .exclude(pk=settings.SYSTEM_SETTINGS_RESOURCE_MODEL_ID)
            .select_related("resource_instance_lifecycle")
            .prefetch_related(
                "resource_instance_lifecycle__resource_instance_lifecycle_states"
            )
        )
        resource_models = []
        for graph in graphs:
            lifecycle = graph.resource_instance_lifecycle
            states = (
                lifecycle.resource_instance_lifecycle_states.all() if lifecycle else []
            )
            resource_models.append(
                {
                    "graphid": str(graph.pk),
                    "name": str(graph.name),
                    "lifecycle_states": [
                        {"id": str(state.pk), "name": str(state.name)}
                        for state in states
                    ],
                }
            )
        resource_models.sort(key=lambda model: model["name"].lower())
        return JSONResponse({"resource_models": resource_models})


class ResourceSetsView(SuperuserAPIView):
    def get(self, request):
        if not apps.is_installed("arches_resource_sets"):
            return JSONResponse({"resource_sets": []})
        from arches_resource_sets.models import ResourceSet

        resource_sets = [
            {"id": str(resource_set.pk), "name": str(resource_set.description or "")}
            for resource_set in ResourceSet.objects.all()
        ]
        resource_sets.sort(key=lambda resource_set: resource_set["name"].lower())
        return JSONResponse({"resource_sets": resource_sets})


def serialize_node(node):
    config = node.config or {}
    data = {
        "nodeid": str(node.pk),
        "name": node.name,
        "alias": node.alias,
        "datatype": node.datatype,
    }
    if node.datatype in ("domain-value", "domain-value-list"):
        data["options"] = [
            {
                "id": str(option.get("id")),
                "label": get_localized_value(option.get("text", "")),
            }
            for option in config.get("options") or []
        ]
    elif node.datatype == "boolean":
        data["true_label"] = get_localized_value(config.get("trueLabel") or "") or _(
            "True"
        )
        data["false_label"] = get_localized_value(config.get("falseLabel") or "") or _(
            "False"
        )
    elif node.datatype == "date":
        data["date_format"] = config.get("dateFormat") or ""
    elif node.datatype == "reference":
        list_id = config.get("controlledList")
        data["controlled_list_id"] = str(list_id) if list_id else None
    return data


class ResourceModelNodesView(SuperuserAPIView):
    def get(self, request, graph_id):
        nodes = Node.objects.filter(
            graph_id=graph_id,
            graph__isresource=True,
            datatype__in=get_supported_datatypes(),
        )
        serialized = [serialize_node(node) for node in nodes]
        serialized.sort(key=lambda node: node["name"].lower())
        return JSONResponse({"nodes": serialized})


class LanguagesView(SuperuserAPIView):
    def get(self, request):
        languages = Language.objects.order_by("name")
        return JSONResponse(
            {
                "languages": [
                    {"code": language.code, "name": language.name}
                    for language in languages
                ]
            }
        )


class ControlledListItemsView(SuperuserAPIView):
    def get(self, request, list_id):
        if not apps.is_installed("arches.extensions.controlled_lists"):
            return JSONResponse({"items": []})
        from arches.extensions.controlled_lists.models import ListItem

        items = ListItem.objects.filter(list_id=list_id).with_list_item_labels()
        children = {}
        for item in items:
            children.setdefault(item.parent_id, []).append(item)

        # Depth-first, so children follow their parent.
        flattened = []

        def visit(parent_id, depth):
            for item in sorted(children.get(parent_id, []), key=lambda i: i.sortorder):
                flattened.append(
                    {
                        "id": str(item.pk),
                        "label": item.find_best_label() or item.uri,
                        "depth": depth,
                    }
                )
                visit(item.pk, depth + 1)

        visit(None, 0)
        return JSONResponse({"items": flattened})


def serialize_group(group):
    return {"id": group.pk, "name": group.name, "member_count": group.user_set.count()}


class GroupsView(SuperuserAPIView):
    def get(self, request):
        groups = Group.objects.order_by("name")
        return JSONResponse({"groups": [serialize_group(group) for group in groups]})

    def post(self, request):
        name = self.get_json_body(request).get("name")
        if not isinstance(name, str) or not name.strip():
            raise BadRequest(_("A group name is required."))
        name = name.strip()
        if len(name) > GROUP_NAME_MAX_LENGTH:
            raise BadRequest(_("The group name is too long."))
        try:
            with transaction.atomic():
                group = Group.objects.create(name=name)
        except IntegrityError:
            return JSONErrorResponse(
                message=_("A group with this name already exists."),
                status=HTTPStatus.CONFLICT,
            )
        return JSONResponse(serialize_group(group), status=HTTPStatus.CREATED)


class GroupView(SuperuserAPIView):
    def delete(self, request, group_id):
        try:
            group = Group.objects.get(pk=group_id)
        except Group.DoesNotExist:
            return JSONErrorResponse(
                message=_("Group not found."), status=HTTPStatus.NOT_FOUND
            )
        if group.user_set.exists():
            return JSONErrorResponse(
                message=_("A group with members cannot be deleted."),
                status=HTTPStatus.CONFLICT,
            )
        group.delete()
        return HttpResponse(status=HTTPStatus.NO_CONTENT)
