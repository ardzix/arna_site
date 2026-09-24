"""Add the immutable UUID used as the Arnatech cross-service tenant ID."""

import uuid

from django.db import migrations, models


def populate_public_ids(apps, schema_editor):
    Tenant = apps.get_model("core", "Tenant")
    for tenant in Tenant.objects.filter(public_id__isnull=True).iterator():
        tenant.public_id = uuid.uuid4()
        tenant.save(update_fields=["public_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_tenant_org_non_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="public_id",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True, unique=True),
        ),
        migrations.RunPython(populate_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tenant",
            name="public_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
