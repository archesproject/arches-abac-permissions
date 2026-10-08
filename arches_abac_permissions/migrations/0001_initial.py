import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InclusionRule",
            fields=[
                (
                    "inclusionruleid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.TextField()),
                ("modulename", models.TextField(blank=True, null=True)),
                ("classname", models.TextField(blank=True, null=True)),
                ("definition", models.JSONField()),
                ("created", models.DateTimeField(auto_now_add=True)),
                (
                    "owner",
                    models.ForeignKey(
                        db_column="owner_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "inclusion_rules",
                "managed": True,
            },
        ),
        migrations.CreateModel(
            name="InclusionRuleGroupPermission",
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
                        related_name="inclusion_rule_permissions",
                        to="auth.group",
                    ),
                ),
                (
                    "permissions",
                    models.ManyToManyField(
                        blank=True,
                        related_name="inclusion_rule_group_permissions",
                        to="auth.permission",
                    ),
                ),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="group_permissions",
                        to="arches_abac_permissions.inclusionrule",
                    ),
                ),
            ],
            options={
                "db_table": "inclusion_rule_group_permissions",
                "managed": True,
            },
        ),
        migrations.AddConstraint(
            model_name="inclusionrulegrouppermission",
            constraint=models.UniqueConstraint(
                fields=("rule", "group"), name="unique_inclusion_rule_group"
            ),
        ),
        migrations.CreateModel(
            name="SearchRule",
            fields=[],
            options={"proxy": True, "indexes": [], "constraints": []},
            bases=("arches_abac_permissions.inclusionrule",),
        ),
        migrations.CreateModel(
            name="QuerySetRule",
            fields=[],
            options={"proxy": True, "indexes": [], "constraints": []},
            bases=("arches_abac_permissions.inclusionrule",),
        ),
    ]
