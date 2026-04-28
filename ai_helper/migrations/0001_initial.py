# Generated manually for ai_helper initial schema

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AICopilotSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('mode', models.CharField(choices=[('template', 'Template Builder'), ('site', 'Site Content Builder')], max_length=20)),
                ('status', models.CharField(choices=[('active', 'Active'), ('generated', 'Generated'), ('published', 'Published'), ('failed', 'Failed')], default='active', max_length=20)),
                ('title', models.CharField(blank=True, max_length=255)),
                ('created_by_user_id', models.CharField(max_length=64)),
                ('created_by_email', models.CharField(blank=True, max_length=255)),
                ('selected_template_id', models.UUIDField(blank=True, null=True)),
                ('context_summary', models.TextField(blank=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='AIGenerationDraft',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('draft_type', models.CharField(choices=[('template', 'Template Draft'), ('site_content', 'Site Content Draft'), ('fe_guide', 'Frontend Guide Draft')], max_length=20)),
                ('payload_json', models.JSONField(blank=True, default=dict)),
                ('markdown_text', models.TextField(blank=True)),
                ('validation_report_json', models.JSONField(blank=True, default=dict)),
                ('is_selected', models.BooleanField(default=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='drafts', to='ai_helper.aicopilotsession')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='AICopilotMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('role', models.CharField(choices=[('user', 'User'), ('assistant', 'Assistant'), ('system', 'System')], max_length=20)),
                ('content', models.TextField()),
                ('seq', models.PositiveIntegerField(default=0)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='ai_helper.aicopilotsession')),
            ],
            options={
                'ordering': ['seq', 'created_at'],
                'unique_together': {('session', 'seq')},
            },
        ),
        migrations.CreateModel(
            name='AICopilotAttachment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('type', models.CharField(choices=[('image', 'Image')], default='image', max_length=20)),
                ('url', models.URLField()),
                ('mime_type', models.CharField(max_length=100)),
                ('caption', models.CharField(blank=True, max_length=1000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='ai_helper.aicopilotmessage')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
    ]
