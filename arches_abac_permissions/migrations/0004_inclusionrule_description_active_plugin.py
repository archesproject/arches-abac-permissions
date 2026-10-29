import uuid

from django.db import migrations, models

from arches.app.models.fields.i18n import I18n_String

PLUGIN_ID = uuid.UUID("450df458-06ca-401d-b2d0-e67d08e8d99d")
PLUGIN_SLUG = "rule-permissions"


def add_plugin(apps, schema_editor):
    Plugin = apps.get_model("models", "Plugin")
    Plugin(
        pluginid=PLUGIN_ID,
        name=I18n_String("Rule Permissions"),
        icon="fa fa-shield",
        component="views/components/plugins/rule-permissions",
        componentname="rule-permissions",
        config={"show": True},
        slug=PLUGIN_SLUG,
        sortorder=0,
    ).save()


def remove_plugin(apps, schema_editor):
    Plugin = apps.get_model("models", "Plugin")
    Plugin.objects.filter(slug=PLUGIN_SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("models", "10999_update_principaluser"),
        ("arches_abac_permissions", "0003_resourcesetrule"),
    ]

    operations = [
        migrations.AddField(
            model_name="inclusionrule",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="inclusionrule",
            name="active",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(add_plugin, remove_plugin),
    ]
