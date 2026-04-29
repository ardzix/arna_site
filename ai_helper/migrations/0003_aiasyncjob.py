import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ai_helper', '0002_session_llm_mode_and_model'),
    ]

    operations = [
        migrations.CreateModel(
            name='AIAsyncJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('operation', models.CharField(choices=[('generate', 'Generate Drafts'), ('publish', 'Publish Draft')], max_length=20)),
                ('status', models.CharField(choices=[('asking', 'Asking'), ('thinking', 'Thinking'), ('done', 'Done'), ('failed', 'Failed')], default='asking', max_length=20)),
                ('q_task_id', models.CharField(blank=True, max_length=64)),
                ('input_json', models.JSONField(blank=True, default=dict)),
                ('result_json', models.JSONField(blank=True, default=dict)),
                ('error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='jobs', to='ai_helper.aicopilotsession')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
