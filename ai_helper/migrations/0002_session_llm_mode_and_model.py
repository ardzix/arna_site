from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_helper', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='aicopilotsession',
            name='llm_mode',
            field=models.CharField(
                choices=[
                    ('chat_economy', 'Chat Economy (Text-Only)'),
                    ('multimodal_vision', 'Multimodal Vision'),
                ],
                default='chat_economy',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='aicopilotsession',
            name='llm_model',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
