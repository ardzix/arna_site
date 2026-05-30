"""Module for ai_helper.admin."""
from django.contrib import admin

from ai_helper.models import (
    AICopilotSession,
    AICopilotMessage,
    AICopilotAttachment,
    AIGenerationDraft,
    AIAsyncJob,
)


@admin.register(AICopilotSession)
class AICopilotSessionAdmin(admin.ModelAdmin):
    """AICopilotSessionAdmin class."""
    list_display = ('id', 'mode', 'llm_mode', 'status', 'created_by_email', 'created_at')
    list_filter = ('mode', 'llm_mode', 'status')
    search_fields = ('id', 'created_by_email', 'created_by_user_id', 'title')


@admin.register(AICopilotMessage)
class AICopilotMessageAdmin(admin.ModelAdmin):
    """AICopilotMessageAdmin class."""
    list_display = ('id', 'session', 'role', 'seq', 'created_at')
    list_filter = ('role',)


@admin.register(AICopilotAttachment)
class AICopilotAttachmentAdmin(admin.ModelAdmin):
    """AICopilotAttachmentAdmin class."""
    list_display = ('id', 'message', 'type', 'mime_type', 'created_at')
    list_filter = ('type',)


@admin.register(AIGenerationDraft)
class AIGenerationDraftAdmin(admin.ModelAdmin):
    """AIGenerationDraftAdmin class."""
    list_display = ('id', 'session', 'draft_type', 'version', 'is_selected', 'created_at')
    list_filter = ('draft_type', 'is_selected')


@admin.register(AIAsyncJob)
class AIAsyncJobAdmin(admin.ModelAdmin):
    """AIAsyncJobAdmin class."""
    list_display = ('id', 'session', 'operation', 'status', 'q_task_id', 'created_at')
    list_filter = ('operation', 'status')
