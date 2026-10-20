from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("storage", "0001_initial")]
    operations = [migrations.AddField(model_name="mediareference", name="tenant_id",
        field=models.UUIDField(blank=True, db_index=True, null=True))]
