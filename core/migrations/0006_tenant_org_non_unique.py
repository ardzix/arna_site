from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_domain_flags_for_fe_be_mapping"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenant",
            name="sso_organization_id",
            field=models.CharField(db_index=True, max_length=255),
        ),
    ]

