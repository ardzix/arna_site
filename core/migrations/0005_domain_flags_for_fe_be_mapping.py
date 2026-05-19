from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_tenant_plan_tenancy_mode_shared_pool_and_schema_non_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="domain",
            name="role",
            field=models.CharField(
                choices=[
                    ("backend_primary", "Backend Primary"),
                    ("frontend_default", "Frontend Default"),
                    ("frontend_custom", "Frontend Custom"),
                ],
                db_index=True,
                default="frontend_custom",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="domain",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("pending_verification", "Pending Verification"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="active",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="domain",
            name="is_primary_frontend",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="domain",
            name="target_backend_domain",
            field=models.CharField(blank=True, default="", max_length=253),
        ),
        migrations.AddField(
            model_name="domain",
            name="verification_method",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="domain",
            name="verification_token",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="domain",
            name="verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

