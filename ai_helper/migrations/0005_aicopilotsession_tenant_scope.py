"""Add tenant/org scope columns for AI session isolation."""
from django.db import migrations, models


class Migration(migrations.Migration):
    """Migration for tenant/org scoped AI sessions."""

    dependencies = [
        ("ai_helper", "0004_alter_aiasyncjob_operation"),
    ]

    operations = [
        migrations.AddField(
            model_name="aicopilotsession",
            name="organization_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="aicopilotsession",
            name="tenant_slug",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100),
        ),
    ]

