import uuid
from django.db import models


class AICopilotSession(models.Model):
    MODE_TEMPLATE = 'template'
    MODE_SITE = 'site'
    MODE_CHOICES = [
        (MODE_TEMPLATE, 'Template Builder'),
        (MODE_SITE, 'Site Content Builder'),
    ]

    STATUS_ACTIVE = 'active'
    STATUS_GENERATED = 'generated'
    STATUS_PUBLISHED = 'published'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_GENERATED, 'Generated'),
        (STATUS_PUBLISHED, 'Published'),
        (STATUS_FAILED, 'Failed'),
    ]

    LLM_MODE_CHAT_ECONOMY = 'chat_economy'
    LLM_MODE_MULTIMODAL_VISION = 'multimodal_vision'
    LLM_MODE_CHOICES = [
        (LLM_MODE_CHAT_ECONOMY, 'Chat Economy (Text-Only)'),
        (LLM_MODE_MULTIMODAL_VISION, 'Multimodal Vision'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    llm_mode = models.CharField(max_length=32, choices=LLM_MODE_CHOICES, default=LLM_MODE_CHAT_ECONOMY)
    llm_model = models.CharField(max_length=100, blank=True)
    title = models.CharField(max_length=255, blank=True)
    created_by_user_id = models.CharField(max_length=64)
    created_by_email = models.CharField(max_length=255, blank=True)
    selected_template_id = models.UUIDField(null=True, blank=True)
    context_summary = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class AICopilotMessage(models.Model):
    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    ROLE_SYSTEM = 'system'
    ROLE_CHOICES = [
        (ROLE_USER, 'User'),
        (ROLE_ASSISTANT, 'Assistant'),
        (ROLE_SYSTEM, 'System'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AICopilotSession, related_name='messages', on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    seq = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['seq', 'created_at']
        unique_together = [('session', 'seq')]


class AICopilotAttachment(models.Model):
    TYPE_IMAGE = 'image'
    TYPE_CHOICES = [(TYPE_IMAGE, 'Image')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(AICopilotMessage, related_name='attachments', on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_IMAGE)
    url = models.URLField()
    mime_type = models.CharField(max_length=100)
    caption = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class AIGenerationDraft(models.Model):
    TYPE_TEMPLATE = 'template'
    TYPE_SITE_CONTENT = 'site_content'
    TYPE_FE_GUIDE = 'fe_guide'
    TYPE_CHOICES = [
        (TYPE_TEMPLATE, 'Template Draft'),
        (TYPE_SITE_CONTENT, 'Site Content Draft'),
        (TYPE_FE_GUIDE, 'Frontend Guide Draft'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AICopilotSession, related_name='drafts', on_delete=models.CASCADE)
    draft_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    payload_json = models.JSONField(default=dict, blank=True)
    markdown_text = models.TextField(blank=True)
    validation_report_json = models.JSONField(default=dict, blank=True)
    is_selected = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
