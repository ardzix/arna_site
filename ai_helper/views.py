from django.shortcuts import get_object_or_404
import uuid
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db import connection
from django_q.tasks import async_task

from authentication.permissions import IsTenantMember, IsTenantAdmin, IsTenantOwner
from ai_helper.models import AICopilotSession, AIGenerationDraft, AIAsyncJob
from core.models import Template
from ai_helper.serializers import (
    AICopilotSessionCreateSerializer,
    AICopilotSessionSerializer,
    AICopilotSessionListSerializer,
    AICopilotMessageCreateSerializer,
    AIGenerationDraftSerializer,
    AIGenerateRequestSerializer,
    AIPublishRequestSerializer,
    AIAsyncJobSerializer,
)
from ai_helper.services import (
    add_user_message,
)


READ_METHODS = {'GET'}


def _json_safe(value):
    """Convert serializer validated data into JSONField-safe primitives."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


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

    @swagger_auto_schema(
        operation_summary='List AI Copilot sessions (sidebar payload)',
        operation_description=(
            "Return lightweight session items for sidebar list with load-more pagination. "
            "This endpoint intentionally excludes full message history."
        ),
        manual_parameters=[
            openapi.Parameter(
                'limit',
                openapi.IN_QUERY,
                description='Number of items per page (default: 20, max: 100).',
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                'offset',
                openapi.IN_QUERY,
                description='Start index for pagination (default: 0).',
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'items': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_OBJECT)),
                    'limit': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'offset': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'next_offset': openapi.Schema(type=openapi.TYPE_INTEGER, x_nullable=True),
                    'has_more': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    'total': openapi.Schema(type=openapi.TYPE_INTEGER),
                },
            ),
        },
        security=[{'Bearer': []}],
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get('limit', 20))
        except (TypeError, ValueError):
            limit = 20
        try:
            offset = int(request.query_params.get('offset', 0))
        except (TypeError, ValueError):
            offset = 0

        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        qs = AICopilotSession.objects.order_by('-created_at')
        total = qs.count()
        sessions = qs[offset:offset + limit]
        items = AICopilotSessionListSerializer(sessions, many=True).data

        next_offset = offset + limit if (offset + limit) < total else None
        return Response(
            {
                'items': items,
                'limit': limit,
                'offset': offset,
                'next_offset': next_offset,
                'has_more': next_offset is not None,
                'total': total,
            }
        )

    @swagger_auto_schema(
        operation_summary='Create AI Copilot session',
        operation_description=(
            "Create a new tenant-scoped AI session.\n\n"
            "Use `mode=template` to build reusable template structure.\n"
            "Use `mode=site` to build site content based on existing template reference.\n"
            "For `mode=site`, submit one of:\n"
            "- `template_id` (published template UUID), or\n"
            "- `template_draft_id` (AI template draft UUID fallback).\n"
            "If both are provided, backend uses `template_id` and stores draft input for traceability.\n\n"
            "Next step:\n"
            "1) POST `/api/ai/sessions/{session_id}/messages/` to start brainstorming.\n"
            "2) Poll `/api/ai/jobs/{job_id}/status/` for assistant reply."
        ),
        request_body=AICopilotSessionCreateSerializer,
        responses={201: AICopilotSessionListSerializer()},
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
            metadata=serializer.validated_data.get('metadata', {}),
            created_by_user_id=str(getattr(user, 'id', '')),
            created_by_email=getattr(user, 'email', ''),
        )
        return Response(AICopilotSessionListSerializer(session).data, status=201)


class AISessionDetailView(APIView):
    """Retrieve a single AI Copilot session with ordered message history."""
    def get_permissions(self):
        return _read_permissions()

    @swagger_auto_schema(
        operation_summary='Get AI Copilot session detail',
        operation_description=(
            "Fetch session metadata and message history.\n\n"
            "Next step:\n"
            "- Continue brainstorming via POST `/api/ai/sessions/{session_id}/messages/`\n"
            "- Or trigger generation via POST `/api/ai/sessions/{session_id}/generate/`"
        ),
        responses={200: AICopilotSessionSerializer()},
        security=[{'Bearer': []}],
    )
    def get(self, request, session_id):
        session = get_object_or_404(AICopilotSession, id=session_id)
        return Response(AICopilotSessionSerializer(session).data)


class AITemplateOptionListView(APIView):
    """List available template identifiers for site-mode session creation."""
    def get_permissions(self):
        return _read_permissions()

    @swagger_auto_schema(
        operation_summary='List available template options for site mode',
        operation_description=(
            "Return available template identifiers without requiring a session_id.\n\n"
            "Includes:\n"
            "- published templates (`template_id`)\n"
            "- AI template drafts (`template_draft_id`)\n\n"
            "Next step:\n"
            "- Use one returned id when creating `mode=site` session via POST `/api/ai/sessions/`."
        ),
        manual_parameters=[
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Items per source list (default 20, max 100).'),
            openapi.Parameter('offset', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Offset per source list (default 0).'),
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='Optional keyword filter for name/slug/title.'),
            openapi.Parameter('selected_only', openapi.IN_QUERY, type=openapi.TYPE_BOOLEAN, description='If true, template_drafts only include selected drafts.'),
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'published_templates': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_OBJECT)),
                    'template_drafts': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_OBJECT)),
                    'limit': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'offset': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'has_more_published': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    'has_more_drafts': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                },
            )
        },
        security=[{'Bearer': []}],
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get('limit', 20))
        except (TypeError, ValueError):
            limit = 20
        try:
            offset = int(request.query_params.get('offset', 0))
        except (TypeError, ValueError):
            offset = 0
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        search = (request.query_params.get('search') or '').strip()
        selected_only = str(request.query_params.get('selected_only', 'false')).lower() in {'1', 'true', 'yes'}

        published_qs = Template.objects.filter(is_active=True, is_published=True)
        if search:
            published_qs = published_qs.filter(Q(name__icontains=search) | Q(slug__icontains=search))
        published_qs = published_qs.order_by('name')
        published_total = published_qs.count()
        published = published_qs[offset:offset + limit]
        published_rows = [
            {
                'template_id': str(t.id),
                'name': t.name,
                'slug': t.slug,
                'category': t.category,
            }
            for t in published
        ]

        drafts_qs = AIGenerationDraft.objects.filter(
            draft_type=AIGenerationDraft.TYPE_TEMPLATE
        ).select_related('session')
        if selected_only:
            drafts_qs = drafts_qs.filter(is_selected=True)
        if search:
            drafts_qs = drafts_qs.filter(session__title__icontains=search)
        drafts_qs = drafts_qs.order_by('-created_at')
        drafts_total = drafts_qs.count()
        drafts = drafts_qs[offset:offset + limit]
        draft_rows = [
            {
                'template_draft_id': str(d.id),
                'session_id': str(d.session_id),
                'session_title': d.session.title,
                'created_at': d.created_at,
                'draft_name': (d.payload_json or {}).get('name', ''),
                'draft_slug': (d.payload_json or {}).get('slug', ''),
            }
            for d in drafts
        ]
        return Response(
            {
                'published_templates': published_rows,
                'template_drafts': draft_rows,
                'limit': limit,
                'offset': offset,
                'has_more_published': (offset + limit) < published_total,
                'has_more_drafts': (offset + limit) < drafts_total,
            }
        )


class AISessionMessageCreateView(APIView):
    """
    Add a user message (with optional image attachments) and enqueue assistant reply.

    In multimodal_vision mode, image attachments are forwarded as native image_url
    content parts to the configured vision-capable model.
    """
    def get_permissions(self):
        return _write_permissions()

    @swagger_auto_schema(
        operation_summary='Add message and enqueue assistant brainstorm reply',
        operation_description=(
            "Append one user message with optional image attachments, then enqueue async assistant reply.\n\n"
            "Response returns `job_id` and `check_status_url`.\n\n"
            "Next step:\n"
            "1) GET `/api/ai/jobs/{job_id}/status/` until `done`.\n"
            "2) Repeat messages as needed.\n"
            "3) When discussion is enough, POST `/api/ai/sessions/{session_id}/generate/`."
        ),
        request_body=AICopilotMessageCreateSerializer,
        responses={
            202: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'job_id': openapi.Schema(type=openapi.TYPE_STRING, format='uuid'),
                    'check_status_url': openapi.Schema(type=openapi.TYPE_STRING),
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

        existing = AIAsyncJob.objects.filter(
            session=session,
            operation=AIAsyncJob.OP_MESSAGE,
            status__in=[AIAsyncJob.STATUS_ASKING, AIAsyncJob.STATUS_THINKING],
        ).order_by('-created_at').first()
        if existing:
            return Response(
                {
                    'status': existing.status,
                    'job_id': str(existing.id),
                    'check_status_url': f'/api/ai/jobs/{existing.id}/status/',
                },
                status=202,
            )

        job = AIAsyncJob.objects.create(
            session=session,
            operation=AIAsyncJob.OP_MESSAGE,
            status=AIAsyncJob.STATUS_ASKING,
            input_json={'source': 'message'},
        )
        try:
            q_id = async_task('ai_helper.tasks.run_ai_job', str(job.id), connection.schema_name)
            job.q_task_id = str(q_id or '')
            job.save(update_fields=['q_task_id'])
        except Exception as exc:
            job.status = AIAsyncJob.STATUS_FAILED
            job.error = f'Failed to enqueue message job: {exc}'
            job.save(update_fields=['status', 'error'])
            return Response({'error': str(job.error)}, status=503)

        return Response(
            {
                'status': AIAsyncJob.STATUS_ASKING,
                'job_id': str(job.id),
                'check_status_url': f'/api/ai/jobs/{job.id}/status/',
            },
            status=202,
        )


class AISessionGenerateView(APIView):
    """Enqueue asynchronous draft generation job for the current session."""
    def get_permissions(self):
        return _write_permissions()

    @swagger_auto_schema(
        operation_summary='Generate AI drafts',
        operation_description=(
            "Enqueue async generation of structured drafts from session context.\n\n"
            "Template mode result: `template_draft_id` and `fe_guide_draft_id`.\n"
            "Site mode result: `site_content_draft_id`.\n\n"
            "Next step:\n"
            "1) GET `/api/ai/jobs/{job_id}/status/` until `done`.\n"
            "2) Review drafts via GET `/api/ai/sessions/{session_id}/drafts/` "
            "or type-specific endpoints.\n"
            "3) Publish via POST `/api/ai/sessions/{session_id}/publish/`."
        ),
        request_body=AIGenerateRequestSerializer,
        responses={
            202: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                    'job_id': openapi.Schema(type=openapi.TYPE_STRING, format='uuid'),
                    'check_status_url': openapi.Schema(type=openapi.TYPE_STRING),
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

        existing = AIAsyncJob.objects.filter(
            session=session,
            operation=AIAsyncJob.OP_GENERATE,
            status__in=[AIAsyncJob.STATUS_ASKING, AIAsyncJob.STATUS_THINKING],
        ).order_by('-created_at').first()

        if existing:
            return Response(
                {
                    'status': existing.status,
                    'job_id': str(existing.id),
                    'check_status_url': f'/api/ai/jobs/{existing.id}/status/',
                },
                status=202,
            )

        job = AIAsyncJob.objects.create(
            session=session,
            operation=AIAsyncJob.OP_GENERATE,
            status=AIAsyncJob.STATUS_ASKING,
            input_json=_json_safe(req.validated_data),
        )
        try:
            q_id = async_task('ai_helper.tasks.run_ai_job', str(job.id), connection.schema_name)
            job.q_task_id = str(q_id or '')
            job.save(update_fields=['q_task_id'])
        except Exception as exc:
            job.status = AIAsyncJob.STATUS_FAILED
            job.error = f'Failed to enqueue generate job: {exc}'
            job.save(update_fields=['status', 'error'])
            return Response({'error': str(job.error)}, status=503)

        return Response(
            {
                'status': AIAsyncJob.STATUS_ASKING,
                'job_id': str(job.id),
                'check_status_url': f'/api/ai/jobs/{job.id}/status/',
            },
            status=202,
        )


class AISessionDraftListView(APIView):
    """List all generated drafts for a session."""
    def get_permissions(self):
        return _read_permissions()

    @swagger_auto_schema(
        operation_summary='List session drafts',
        operation_description=(
            "Return all drafts for the session (`template`, `site_content`, `fe_guide`).\n\n"
            "Next step:\n"
            "- Pick correct draft IDs and call POST `/api/ai/sessions/{session_id}/publish/`."
        ),
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
        operation_description=(
            "Enqueue async publish into production CMS models.\n\n"
            "Mode contract:\n"
            "- `mode=template`: submit `template_draft_id` (required), `fe_guide_draft_id` (optional).\n"
            "- `mode=site`: submit `site_content_draft_id` (required), `overwrite` (optional).\n\n"
            "Next step:\n"
            "1) GET `/api/ai/jobs/{job_id}/status/` until `done`.\n"
            "2) If `template` publish done, template is available in tenant templates.\n"
            "3) If `site` publish done, content is available on public site endpoints."
        ),
        request_body=AIPublishRequestSerializer,
        responses={
            202: openapi.Response('Publish job queued'),
            400: openapi.Response('Publish error'),
        },
        security=[{'Bearer': []}],
    )
    def post(self, request, session_id):
        session = get_object_or_404(AICopilotSession, id=session_id)
        req = AIPublishRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)

        if session.mode == AICopilotSession.MODE_TEMPLATE and not req.validated_data.get('template_draft_id'):
            return Response({'error': 'template_draft_id is required for template mode.'}, status=400)
        if session.mode == AICopilotSession.MODE_SITE and not req.validated_data.get('site_content_draft_id'):
            return Response({'error': 'site_content_draft_id is required for site mode.'}, status=400)

        existing = AIAsyncJob.objects.filter(
            session=session,
            operation=AIAsyncJob.OP_PUBLISH,
            status__in=[AIAsyncJob.STATUS_ASKING, AIAsyncJob.STATUS_THINKING],
        ).order_by('-created_at').first()
        if existing:
            return Response(
                {
                    'status': existing.status,
                    'job_id': str(existing.id),
                    'check_status_url': f'/api/ai/jobs/{existing.id}/status/',
                },
                status=202,
            )

        job = AIAsyncJob.objects.create(
            session=session,
            operation=AIAsyncJob.OP_PUBLISH,
            status=AIAsyncJob.STATUS_ASKING,
            input_json=_json_safe(req.validated_data),
        )
        try:
            q_id = async_task('ai_helper.tasks.run_ai_job', str(job.id), connection.schema_name)
            job.q_task_id = str(q_id or '')
            job.save(update_fields=['q_task_id'])
        except Exception as exc:
            job.status = AIAsyncJob.STATUS_FAILED
            job.error = f'Failed to enqueue publish job: {exc}'
            job.save(update_fields=['status', 'error'])
            return Response({'error': str(job.error)}, status=503)

        return Response(
            {
                'status': AIAsyncJob.STATUS_ASKING,
                'job_id': str(job.id),
                'check_status_url': f'/api/ai/jobs/{job.id}/status/',
            },
            status=202,
        )


class AISessionFEGuideView(APIView):
    """Get FE guide draft payload + markdown for template mode sessions."""
    def get_permissions(self):
        return _read_permissions()

    @swagger_auto_schema(
        operation_summary='Get FE guide for a session',
        operation_description=(
            "Get selected/latest FE guide draft for template-mode session.\n\n"
            "Next step:\n"
            "- Use payload/markdown as frontend implementation reference,\n"
            "- then publish template via POST `/api/ai/sessions/{session_id}/publish/`."
        ),
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


class AIJobStatusView(APIView):
    """Get asynchronous AI job status and result payload (if done)."""
    def get_permissions(self):
        return _read_permissions()

    @swagger_auto_schema(
        operation_summary='Get AI async job status',
        operation_description=(
            "Fetch current status of async AI operation: `asking`, `thinking`, `done`, `failed`.\n\n"
            "When `done`, read `result_json` and continue flow based on operation:\n"
            "- message: read `assistant_reply`.\n"
            "- generate: read generated draft IDs.\n"
            "- publish: read publish result."
        ),
        responses={
            200: AIAsyncJobSerializer(),
            404: openapi.Response('Job not found'),
        },
        security=[{'Bearer': []}],
    )
    def get(self, request, job_id):
        job = get_object_or_404(AIAsyncJob, id=job_id)
        return Response(AIAsyncJobSerializer(job).data)


class AISessionTemplateDraftView(APIView):
    """Get selected/latest template draft for one session."""
    def get_permissions(self):
        return _read_permissions()

    @swagger_auto_schema(
        operation_summary='Get template draft for a session',
        operation_description=(
            "Return selected template draft (or latest) for this session.\n\n"
            "Next step:\n"
            "- Use `id` as `template_draft_id` in POST `/api/ai/sessions/{session_id}/publish/`."
        ),
        responses={200: AIGenerationDraftSerializer(), 404: openapi.Response('Template draft not found')},
        security=[{'Bearer': []}],
    )
    def get(self, request, session_id):
        session = get_object_or_404(AICopilotSession, id=session_id)
        draft = AIGenerationDraft.objects.filter(
            session=session,
            draft_type=AIGenerationDraft.TYPE_TEMPLATE,
            is_selected=True,
        ).first() or AIGenerationDraft.objects.filter(
            session=session,
            draft_type=AIGenerationDraft.TYPE_TEMPLATE,
        ).order_by('-created_at').first()
        if not draft:
            return Response({'error': 'Template draft not found.'}, status=404)
        return Response(AIGenerationDraftSerializer(draft).data)


class AISessionSiteContentDraftView(APIView):
    """Get selected/latest site content draft for one session."""
    def get_permissions(self):
        return _read_permissions()

    @swagger_auto_schema(
        operation_summary='Get site content draft for a session',
        operation_description=(
            "Return selected site-content draft (or latest) for this session.\n\n"
            "Next step:\n"
            "- Use `id` as `site_content_draft_id` in POST `/api/ai/sessions/{session_id}/publish/`."
        ),
        responses={200: AIGenerationDraftSerializer(), 404: openapi.Response('Site content draft not found')},
        security=[{'Bearer': []}],
    )
    def get(self, request, session_id):
        session = get_object_or_404(AICopilotSession, id=session_id)
        draft = AIGenerationDraft.objects.filter(
            session=session,
            draft_type=AIGenerationDraft.TYPE_SITE_CONTENT,
            is_selected=True,
        ).first() or AIGenerationDraft.objects.filter(
            session=session,
            draft_type=AIGenerationDraft.TYPE_SITE_CONTENT,
        ).order_by('-created_at').first()
        if not draft:
            return Response({'error': 'Site content draft not found.'}, status=404)
        return Response(AIGenerationDraftSerializer(draft).data)
