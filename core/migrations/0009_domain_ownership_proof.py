from django.db import migrations, models
import django.db.models.deletion


def require_pending_custom_proof(apps, schema_editor):
    Domain = apps.get_model("core", "Domain")
    Domain.objects.filter(role="frontend_custom", status="pending_verification").update(ownership_proof_required=True)


class Migration(migrations.Migration):
    dependencies = [("core", "0008_domain_crm_tenant")]
    operations = [
        migrations.AddField(model_name="domain", name="ownership_proof_required", field=models.BooleanField(default=False)),
        migrations.RunPython(require_pending_custom_proof, migrations.RunPython.noop),
        migrations.AlterField(model_name="domain", name="ownership_proof_required", field=models.BooleanField(default=True)),
        migrations.CreateModel(
            name="DomainOwnershipAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tenant_public_id", models.UUIDField()), ("organization_id", models.UUIDField()),
                ("actor_id", models.UUIDField()), ("hostname", models.CharField(max_length=253)),
                ("provider", models.CharField(max_length=32)), ("project_id", models.CharField(max_length=100)),
                ("team_id", models.CharField(max_length=100)), ("receipt_hash", models.CharField(max_length=64, unique=True)),
                ("evidence_hash", models.CharField(max_length=64)), ("created_at", models.DateTimeField(auto_now_add=True)),
                ("domain", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ownership_audits", to="core.domain")),
            ],
        ),
    ]
