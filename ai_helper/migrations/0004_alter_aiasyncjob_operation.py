from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_helper', '0003_aiasyncjob'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aiasyncjob',
            name='operation',
            field=models.CharField(
                choices=[
                    ('message', 'Message Reply'),
                    ('generate', 'Generate Drafts'),
                    ('publish', 'Publish Draft'),
                ],
                max_length=20,
            ),
        ),
    ]

