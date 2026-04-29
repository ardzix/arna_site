from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from django_tenants.utils import schema_context

from ai_helper.models import AIAsyncJob, AICopilotSession
from ai_helper.services import (
    generate_drafts,
    publish_template_from_draft,
    publish_site_content_from_draft,
    CopilotServiceError,
)


def run_ai_job(job_id: str, tenant_schema: str):
    """Execute one async AI job inside the correct tenant schema."""
    with schema_context(tenant_schema):
        job = get_object_or_404(AIAsyncJob, id=job_id)

        with transaction.atomic():
            job.status = AIAsyncJob.STATUS_THINKING
            job.started_at = timezone.now()
            job.save(update_fields=['status', 'started_at'])

        try:
            if job.operation == AIAsyncJob.OP_GENERATE:
                result = _run_generate(job)
            elif job.operation == AIAsyncJob.OP_PUBLISH:
                result = _run_publish(job)
            else:
                raise CopilotServiceError(f'Unsupported job operation: {job.operation}')

            with transaction.atomic():
                job.status = AIAsyncJob.STATUS_DONE
                job.result_json = result or {}
                job.error = ''
                job.finished_at = timezone.now()
                job.save(update_fields=['status', 'result_json', 'error', 'finished_at'])

        except Exception as exc:
            with transaction.atomic():
                job.status = AIAsyncJob.STATUS_FAILED
                job.error = str(exc)
                job.finished_at = timezone.now()
                job.save(update_fields=['status', 'error', 'finished_at'])


def _run_generate(job: AIAsyncJob):
    session = get_object_or_404(AICopilotSession, id=job.session_id)
    return generate_drafts(session)


def _run_publish(job: AIAsyncJob):
    session = get_object_or_404(AICopilotSession, id=job.session_id)
    payload = job.input_json or {}

    if session.mode == AICopilotSession.MODE_TEMPLATE:
        template_draft_id = payload.get('template_draft_id')
        if not template_draft_id:
            raise CopilotServiceError('template_draft_id is required for template mode.')
        template = publish_template_from_draft(
            session,
            template_draft_id,
            payload.get('fe_guide_draft_id'),
        )
        return {'status': 'published', 'template_id': str(template.id)}

    if session.mode == AICopilotSession.MODE_SITE:
        site_content_draft_id = payload.get('site_content_draft_id')
        if not site_content_draft_id:
            raise CopilotServiceError('site_content_draft_id is required for site mode.')
        return publish_site_content_from_draft(
            session,
            site_content_draft_id,
            overwrite=bool(payload.get('overwrite', False)),
        )

    raise CopilotServiceError('Unsupported mode.')
