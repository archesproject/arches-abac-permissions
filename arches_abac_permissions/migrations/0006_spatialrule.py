from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("arches_abac_permissions", "0005_tilenodevaluerule"),
    ]

    operations = [
        migrations.CreateModel(
            name="SpatialRule",
            fields=[],
            options={
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("arches_abac_permissions.inclusionrule",),
        ),
    ]
