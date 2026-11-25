from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("arches_abac_permissions", "0006_spatialrule"),
    ]

    operations = [
        migrations.CreateModel(
            name="ElasticsearchRule",
            fields=[],
            options={
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("arches_abac_permissions.inclusionrule",),
        ),
    ]
