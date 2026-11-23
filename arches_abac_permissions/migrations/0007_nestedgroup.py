import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("arches_abac_permissions", "0006_spatialrule"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="NestedGroup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="abac_parent_links",
                        to="auth.group",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="abac_child_links",
                        to="auth.group",
                    ),
                ),
            ],
            options={
                "db_table": "abac_nested_groups",
                "managed": True,
                "constraints": [
                    models.UniqueConstraint(
                        fields=("group", "parent"), name="unique_abac_nested_group"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("group", models.F("parent")), _negated=True
                        ),
                        name="abac_nested_group_not_itself",
                    ),
                ],
            },
        ),
    ]
