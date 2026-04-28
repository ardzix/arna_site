from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from authentication.permissions import IsTenantMember, IsTenantAdmin, IsTenantOwner
from ai_helper.models import AICopilotSession, AIGenerationDraft
from ai_helper.serializers import (
    AICopilotSessionCreateSerializer,
    AICopilotSessionSerializer,
    AICopilotMessageCreateSerializer,
    AIGenerationDraftSerializer,
    AIGenerateRequestSerializer,
    AIPublishRequestSerializer,
)
from ai_helper.services import (
    add_user_message,
    generate_brainstorm_reply,
    generate_drafts,
    CopilotServiceError,
    publish_template_from_draft,
    publish_site_content_from_draft,
)
from ai_helper.validators import SchemaValidationError


READ_METHODS = {'GET'}


def _read_permissions():
    return [IsAuthenticated(), IsTenantMember()]


def _write_permissions():
    return [IsAuthenticated(), IsTenantMember(), (IsTenantAdmin | IsTenantOwner)()]


class AISessionListCreateView(APIView):
    """
    List all AI Copilot sessions for the current tenant, or create a new one.

    POST supports runtime model selection:
    - llm_mode: chat_economy | multimodal_vision
    - llm_model: optional explicit model override (default: deepseek-chat)
    - template_id: optional (default null), required only for site mode generation
    - !important: dont submit template_id if working in template creation mode
    """
    def get_permissions(self):
        if self.request.method in READ_METHODS:
            return _read_permissions()
        return _write_permissions()

    def get(self, request):
        sessions = AICopilotSession.objects.all()
        return Response(AICopilotSessionSerializer(sessions, many=True).data)

    @swagger_auto_schema(
        operation_summary='Create AI Copilot session',
        request_body=AICopilotSessionCreateSerializer,
        responses={201: AICopilotSessionSerializer()},
        security=[{'Bearer': []}],
    )
    def post(self, request):
        serializer = AICopilotSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        session = AICopilotSession.objects.create(
            mode=serializer.validated_data['mode'],
            llm_mode=serializer.validated_data.get(
                'llm_mode',
                AICopilotSession.LLM_MODE_CHAT_ECONOMY,
            ),
            llm_model=serializer.validated_data.get('llm_model', ''),
            title=serializer.validated_data.get('title', ''),
            selected_template_id=serializer.validated_data.get('selected_template_id'),
            created_by_user_id=str(getattr(user, 'id', '')),
            created_by_email=getattr(user, 'email', ''),
        )
        return Response(AICopilotSessionSerializer(session).data, status=201)


class AISessionDetailView(APIView):
    """Retrieve a single AI Copilot session with ordered message history."""
    def get_permissions(self):
        return _read_permissions()

    @swagger_auto_schema(
        operation_summary='Get AI Copilot session detail',
        responses={200: AICopilotSessionSerializer()},
        security=[{'Bearer': []}],
    )
    def get(self, request, session_id):
        session = get_object_or_404(AICopilotSession, id=session_id)
        return Response(AICopilotSessionSerializer(session).data)


class AISessionMessageCreateView(APIView):
    """
    Add a user message (with optional image attachments) and return assistant reply.

    In multimodal_vision mode, image attachments are forwarded as native image_url
    content parts to the configured vision-capable model.
    """
    def get_permissions(self):
        return _write_permissions()

    @swagger_auto_schema(
        operation_summary='Add message and get assistant brainstorm reply',
        request_body=AICopilotMessageCreateSerializer,
        responses={
            201: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'assistant_reply': openapi.Schema(type=openapi.TYPE_STRING),
                },
            ),
        },
        security=[{'Bearer': []}],
    )
    def post(self, request, session_id):
        session = get_object_or_404(AICopilotSession, id=session_id)
        serializer = AICopilotMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        add_user_message(
            session=session,
            content=serializer.validated_data['content'],
            attachments=serializer.validated_data.get('attachments', []),
        )

        assistant_reply = generate_brainstorm_reply(session)
        return Response({'status': 'ok', 'assistant_reply': assistant_reply}, status=201)


class AISessionGenerateView(APIView):
    """Generate schema-validated drafts for the current session mode."""
    def get_permissions(self):
        return _write_permissions()

    @swagger_auto_schema(
        operation_summary='Generate AI drafts',
        request_body=AIGenerateRequestSerializer,
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'template_draft_id': openapi.Schema(type=openapi.TYPE_STRING, format='uuid'),
                    'fe_guide_draft_id': openapi.Schema(type=openapi.TYPE_STRING, format='uuid'),
                    'site_content_draft_id': openapi.Schema(type=openapi.TYPE_STRING, format='uuid'),
                },
            ),
            400: openapi.Response('Validation or generation error'),
        },
        security=[{'Bearer': []}],
    )
    def post(self, request, session_id):
        session = get_object_or_404(AICopilotSession, id=session_id)
        req = AIGenerateRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)

        try:
            result = generate_drafts(session)
            return Response({'status': 'generated', **result})
        except (CopilotServiceError, SchemaValidationError) as exc:
            session.status = AICopilotSession.STATUS_FAILED
            session.save(update_fields=['status', 'updated_at'])
            return Response({'error': str(exc)}, status=400)


class AISessionDraftListView(APIView):
    """List all generated drafts for a session."""
    def get_permissions(self):
        return _read_permissions()

    @swagger_auto_schema(
        operation_summary='List session drafts',
        responses={200: AIGenerationDraftSerializer(many=True)},
        security=[{'Bearer': []}],
    )
    def get(self, request, session_id):
        session = get_object_or_404(AICopilotSession, id=session_id)
        drafts = AIGenerationDraft.objects.filter(session=session)
        return Response(AIGenerationDraftSerializer(drafts, many=True).data)


class AISessionPublishView(APIView):
    """
    Publish selected draft(s) into production CMS models.

    - template mode requires template_draft_id
    - site mode requires site_content_draft_id
    """
    def get_permissions(self):
        return _write_permissions()

    @swagger_auto_schema(
        operation_summary='Publish AI draft(s)',
        request_body=AIPublishRequestSerializer,
        responses={
            200: openapi.Response('Publish success'),
            400: openapi.Response('Publish error'),
        },
        security=[{'Bearer': []}],
    )
    def post(self, request, session_id):
        session = get_object_or_404(AICopilotSession, id=session_id)
        req = AIPublishRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)

        try:
            if session.mode == AICopilotSession.MODE_TEMPLATE:
                if not req.validated_data.get('template_draft_id'):
                    return Response({'error': 'template_draft_id is required for template mode.'}, status=400)
                template = publish_template_from_draft(
                    session,
                    req.validated_data['template_draft_id'],
                    req.validated_data.get('fe_guide_draft_id'),
                )
                return Response({'status': 'published', 'template_id': str(template.id)})

            if session.mode == AICopilotSession.MODE_SITE:
                if not req.validated_data.get('site_content_draft_id'):
                    return Response({'error': 'site_content_draft_id is required for site mode.'}, status=400)
                result = publish_site_content_from_draft(
                    session,
                    req.validated_data['site_content_draft_id'],
                    overwrite=req.validated_data.get('overwrite', False),
                )
                return Response(result)

            return Response({'error': 'Unsupported mode.'}, status=400)

        except (CopilotServiceError, SchemaValidationError) as exc:
            return Response({'error': str(exc)}, status=400)


class AISessionFEGuideView(APIView):
    """Get FE guide draft payload + markdown for template mode sessions."""
    def get_permissions(self):
        return _read_permissions()

    @swagger_auto_schema(
        operation_summary='Get FE guide for a session',
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'draft_id': openapi.Schema(type=openapi.TYPE_STRING, format='uuid'),
                    'markdown': openapi.Schema(type=openapi.TYPE_STRING),
                    'payload': openapi.Schema(type=openapi.TYPE_OBJECT),
                },
            ),
            404: openapi.Response('FE guide draft not found'),
        },
        security=[{'Bearer': []}],
    )
    def get(self, request, session_id):
        session = get_object_or_404(AICopilotSession, id=session_id)
        draft = AIGenerationDraft.objects.filter(
            session=session,
            draft_type=AIGenerationDraft.TYPE_FE_GUIDE,
            is_selected=True,
        ).first() or AIGenerationDraft.objects.filter(
            session=session,
            draft_type=AIGenerationDraft.TYPE_FE_GUIDE,
        ).order_by('-created_at').first()

        if not draft:
            return Response({'error': 'FE guide draft not found.'}, status=404)

        return Response({
            'draft_id': str(draft.id),
            'markdown': draft.markdown_text,
            'payload': draft.payload_json,
        })
