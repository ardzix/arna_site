import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0007_tenant_public_id")]
    operations = [
        migrations.AddField(
            model_name="domain", name="crm_tenant",
            field=models.ForeignKey(
                to="core.tenant", on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True, related_name="crm_website_domains",
                help_text="Optional CRM inbox in the same organization; does not change website ownership.",
            ),
        ),
    ]
