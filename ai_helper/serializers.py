from rest_framework import serializers
from ai_helper.models import (
    AICopilotSession,
    AICopilotMessage,
    AICopilotAttachment,
    AIGenerationDraft,
)


class AICopilotSessionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AICopilotSession
        fields = ['mode', 'llm_mode', 'llm_model', 'title', 'selected_template_id']


class AICopilotAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AICopilotAttachment
        fields = ['id', 'type', 'url', 'mime_type', 'caption', 'created_at']
        read_only_fields = ['id', 'created_at']


class AICopilotMessageCreateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=['user'])
    content = serializers.CharField(max_length=20000)
    attachments = AICopilotAttachmentSerializer(many=True, required=False)


class AICopilotMessageSerializer(serializers.ModelSerializer):
    attachments = AICopilotAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = AICopilotMessage
        fields = ['id', 'role', 'content', 'seq', 'metadata', 'attachments', 'created_at']


class AIGenerationDraftSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIGenerationDraft
        fields = [
            'id',
            'draft_type',
            'payload_json',
            'markdown_text',
            'validation_report_json',
            'is_selected',
            'version',
            'metadata',
            'created_at',
            'updated_at',
        ]


class AICopilotSessionSerializer(serializers.ModelSerializer):
    messages = AICopilotMessageSerializer(many=True, read_only=True)

    class Meta:
        model = AICopilotSession
        fields = [
            'id',
            'mode',
            'status',
            'llm_mode',
            'llm_model',
            'title',
            'created_by_user_id',
            'created_by_email',
            'selected_template_id',
            'context_summary',
            'metadata',
            'messages',
            'created_at',
            'updated_at',
        ]


class AIGenerateRequestSerializer(serializers.Serializer):
    regenerate = serializers.BooleanField(required=False, default=False)


class AIPublishRequestSerializer(serializers.Serializer):
    template_draft_id = serializers.UUIDField(required=False)
    site_content_draft_id = serializers.UUIDField(required=False)
    fe_guide_draft_id = serializers.UUIDField(required=False)
    overwrite = serializers.BooleanField(required=False, default=False)
