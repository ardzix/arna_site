from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sites", "0003_page_source_template_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="page",
            name="tenant_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="section",
            name="tenant_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="page",
            name="slug",
            field=models.SlugField(max_length=255),
        ),
        migrations.AddIndex(
            model_name="page",
            index=models.Index(fields=["tenant_id", "slug"], name="sites_page_tenant__7216d6_idx"),
        ),
        migrations.AddIndex(
            model_name="page",
            index=models.Index(fields=["tenant_id", "is_active"], name="sites_page_tenant__dd6d5d_idx"),
        ),
    ]
