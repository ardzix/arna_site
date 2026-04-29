from rest_framework import serializers
import re
from ai_helper.models import (
    AICopilotSession,
    AICopilotMessage,
    AICopilotAttachment,
    AIGenerationDraft,
    AIAsyncJob,
)


class AICopilotSessionCreateSerializer(serializers.ModelSerializer):
    llm_mode = serializers.ChoiceField(
        choices=AICopilotSession.LLM_MODE_CHOICES,
        default=AICopilotSession.LLM_MODE_CHAT_ECONOMY,
        help_text=(
            "LLM runtime mode. "
            "`chat_economy` = text-first token-saving mode. "
            "`multimodal_vision` = native image_url input mode."
        ),
    )
    llm_model = serializers.CharField(
        required=False,
        allow_blank=True,
        default='deepseek-chat',
        help_text=(
            "Optional model override for this session. "
            "Leave empty to use server default model from environment."
        ),
    )
    template_id = serializers.UUIDField(
        source='selected_template_id',
        required=False,
        allow_null=True,
        default=None,
        help_text=(
            "Template UUID used in `site` mode generation. "
            "Use null for `template` mode."
        ),
    )

    class Meta:
        model = AICopilotSession
        fields = ['mode', 'llm_mode', 'llm_model', 'title', 'template_id']


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
    template_id = serializers.UUIDField(source='selected_template_id', allow_null=True, read_only=True)

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
            'template_id',
            'context_summary',
            'metadata',
            'messages',
            'created_at',
            'updated_at',
        ]


class AICopilotSessionListSerializer(serializers.ModelSerializer):
    template_id = serializers.UUIDField(source='selected_template_id', allow_null=True, read_only=True)
    subtitle = serializers.SerializerMethodField()

    class Meta:
        model = AICopilotSession
        fields = [
            'id',
            'mode',
            'status',
            'title',
            'template_id',
            'subtitle',
            'created_at',
            'updated_at',
        ]

    def get_subtitle(self, obj):
        last_ai = obj.messages.filter(role=AICopilotMessage.ROLE_ASSISTANT).order_by('-seq', '-created_at').first()
        if not last_ai:
            return ''
        text = (last_ai.content or '').strip()
        # Keep sidebar subtitle clean: remove common markdown markers and collapse whitespace.
        text = re.sub(r'[`*_#>\[\]\(\)\-~|]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) <= 160:
            return text
        return f'{text[:157].rstrip()}...'


class AIGenerateRequestSerializer(serializers.Serializer):
    regenerate = serializers.BooleanField(required=False, default=False)


class AIPublishRequestSerializer(serializers.Serializer):
    template_draft_id = serializers.UUIDField(required=False)
    site_content_draft_id = serializers.UUIDField(required=False)
    fe_guide_draft_id = serializers.UUIDField(required=False)
    overwrite = serializers.BooleanField(required=False, default=False)


class AIAsyncJobSerializer(serializers.ModelSerializer):
    check_status_url = serializers.SerializerMethodField()

    class Meta:
        model = AIAsyncJob
        fields = [
            'id',
            'operation',
            'status',
            'session',
            'result_json',
            'error',
            'created_at',
            'started_at',
            'finished_at',
            'check_status_url',
        ]

    def get_check_status_url(self, obj):
        return f"/api/ai/jobs/{obj.id}/status/"
