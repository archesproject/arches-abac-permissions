from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("arches_abac_permissions", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="LifecycleStateRule",
            fields=[],
            options={"proxy": True, "indexes": [], "constraints": []},
            bases=("arches_abac_permissions.inclusionrule",),
        ),
    ]
