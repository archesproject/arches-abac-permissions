from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("arches_abac_permissions", "0007_elasticsearchrule"),
    ]

    operations = [
        migrations.CreateModel(
            name="CombinedRule",
            fields=[],
            options={
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("arches_abac_permissions.inclusionrule",),
        ),
    ]
