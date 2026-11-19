import uuid

from django.core.exceptions import ValidationError
from django.db import migrations

MODULENAME = "tile_node_value_rule.py"
CLASSNAME = "TileNodeValueRule"
UUID_DATATYPES = ("resource-instance", "resource-instance-list", "reference")
STORED_KEYS = ("nodegroupid", "datatype")


def tile_rules(apps):
    InclusionRule = apps.get_model("arches_abac_permissions", "InclusionRule")
    return InclusionRule.objects.filter(modulename=MODULENAME, classname=CLASSNAME)


def store_node_keys(apps, schema_editor):
    Node = apps.get_model("models", "Node")
    for rule in tile_rules(apps):
        definition = rule.definition
        try:
            node = Node.objects.get(
                pk=definition["nodeid"], graph_id=definition["graphid"]
            )
        except (KeyError, ValueError, ValidationError, Node.DoesNotExist):
            continue
        definition["nodegroupid"] = str(node.nodegroup_id)
        definition["datatype"] = node.datatype
        if node.datatype in UUID_DATATYPES:
            try:
                definition["value"] = str(uuid.UUID(str(definition.get("value"))))
            except ValueError:
                pass
        rule.save(update_fields=["definition"])


def remove_node_keys(apps, schema_editor):
    for rule in tile_rules(apps):
        for key in STORED_KEYS:
            rule.definition.pop(key, None)
        rule.save(update_fields=["definition"])


class Migration(migrations.Migration):

    dependencies = [
        ("models", "10999_update_principaluser"),
        ("arches_abac_permissions", "0006_spatialrule"),
    ]

    operations = [migrations.RunPython(store_node_keys, remove_node_keys)]
