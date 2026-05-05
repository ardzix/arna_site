from django.db import migrations, models
import django_tenants.postgresql_backend.base


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_template_is_published_template_source_tenant_schema_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tenant',
            name='schema_name',
            field=models.CharField(
                db_index=True,
                max_length=63,
                validators=[django_tenants.postgresql_backend.base._check_schema_name],
            ),
        ),
        migrations.AddField(
            model_name='tenant',
            name='plan',
            field=models.CharField(
                choices=[('free', 'Free'), ('pro', 'Pro'), ('enterprise', 'Enterprise')],
                db_index=True,
                default='free',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='tenant',
            name='tenancy_mode',
            field=models.CharField(
                choices=[('shared', 'Shared'), ('dedicated', 'Dedicated')],
                db_index=True,
                default='shared',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='tenant',
            name='shared_pool_key',
            field=models.CharField(db_index=True, default='pool_shared', max_length=63, blank=True),
        ),
    ]

