from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404

from ai_helper.llm_adapters.deepseek import DeepSeekAdapter
from ai_helper.models import (
    AICopilotSession,
    AICopilotMessage,
    AICopilotAttachment,
    AIGenerationDraft,
)
from ai_helper.validators import validate_payload, SchemaValidationError
from core.models import Template, TemplatePage, TemplateSection, TemplateBlock, TemplateListItem
from sites.models import Page, Section, ContentBlock, ListItem


class CopilotServiceError(Exception):
    """Raised for controlled AI helper service errors exposed to API clients."""
    pass


def next_message_seq(session: AICopilotSession) -> int:
    max_seq = session.messages.aggregate(m=Max('seq'))['m']
    return (max_seq or 0) + 1


def add_user_message(session: AICopilotSession, content: str, attachments: list[dict]):
    with transaction.atomic():
        msg = AICopilotMessage.objects.create(
            session=session,
            role=AICopilotMessage.ROLE_USER,
            content=content,
            seq=next_message_seq(session),
        )
        for att in attachments:
            AICopilotAttachment.objects.create(
                message=msg,
                type=att.get('type', AICopilotAttachment.TYPE_IMAGE),
                url=att['url'],
                mime_type=att['mime_type'],
                caption=att.get('caption', ''),
            )
    return msg


def add_assistant_message(session: AICopilotSession, content: str, metadata: dict | None = None):
    return AICopilotMessage.objects.create(
        session=session,
        role=AICopilotMessage.ROLE_ASSISTANT,
        content=content,
        seq=next_message_seq(session),
        metadata=metadata or {},
    )


def _session_context_text(session: AICopilotSession) -> str:
    chunks = []
    if session.title:
        chunks.append(f'Title: {session.title}')
    if session.context_summary:
        chunks.append(f'Summary: {session.context_summary}')

    for msg in session.messages.prefetch_related('attachments').order_by('seq')[:120]:
        line = f"{msg.role.upper()}: {msg.content}"
        chunks.append(line)
        for att in msg.attachments.all():
            chunks.append(f"ATTACHMENT[{att.type}]: {att.url} ({att.mime_type}) {att.caption}")

    return '\n'.join(chunks)[-60000:]


def _save_draft(session: AICopilotSession, draft_type: str, payload_json=None, markdown_text=''):
    version = (session.drafts.filter(draft_type=draft_type).aggregate(m=Max('version'))['m'] or 0) + 1
    return AIGenerationDraft.objects.create(
        session=session,
        draft_type=draft_type,
        payload_json=payload_json or {},
        markdown_text=markdown_text,
        version=version,
        is_selected=False,
    )


def generate_drafts(session: AICopilotSession):
    """Generate and validate draft artifacts for the given session mode."""
    adapter = DeepSeekAdapter()
    context = _session_context_text(session)
    if not context.strip():
        raise CopilotServiceError('Cannot generate drafts without conversation context.')

    validation_reports = {}

    if session.mode == AICopilotSession.MODE_TEMPLATE:
        try:
            template_payload = adapter.generate_template_draft(context)
        except Exception as exc:
            raise CopilotServiceError(f'Failed to generate template draft JSON: {exc}')
        try:
            validate_payload('template.schema.json', template_payload)
        except SchemaValidationError as first_err:
            # One repair pass for LLM outputs that miss strict schema contract.
            try:
                template_payload = adapter.repair_template_draft(
                    invalid_payload=template_payload,
                    validation_errors=first_err,
                )
            except Exception as exc:
                raise CopilotServiceError(f'Failed to repair template draft JSON: {exc}')
            validate_payload('template.schema.json', template_payload)
        t_draft = _save_draft(session, AIGenerationDraft.TYPE_TEMPLATE, payload_json=template_payload)
        validation_reports['template_draft_id'] = str(t_draft.id)

        try:
            fe_payload = adapter.generate_fe_guide(template_payload)
        except Exception as exc:
            raise CopilotServiceError(f'Failed to generate FE guide JSON: {exc}')
        try:
            validate_payload('fe-guide.schema.json', fe_payload)
        except SchemaValidationError as first_err:
            try:
                fe_payload = adapter.repair_fe_guide_draft(
                    template_payload=template_payload,
                    invalid_payload=fe_payload,
                    validation_errors=first_err,
                )
            except Exception as exc:
                raise CopilotServiceError(f'Failed to repair FE guide JSON: {exc}')
            validate_payload('fe-guide.schema.json', fe_payload)
        g_draft = _save_draft(
            session,
            AIGenerationDraft.TYPE_FE_GUIDE,
            payload_json=fe_payload,
            markdown_text=fe_payload.get('markdown', ''),
        )
        validation_reports['fe_guide_draft_id'] = str(g_draft.id)

    elif session.mode == AICopilotSession.MODE_SITE:
        if not session.selected_template_id:
            raise CopilotServiceError('template_id is required for site mode generation.')
        try:
            site_payload = adapter.generate_site_content_draft(context, session.selected_template_id)
        except Exception as exc:
            raise CopilotServiceError(f'Failed to generate site content JSON: {exc}')
        validate_payload('site-content.schema.json', site_payload)
        s_draft = _save_draft(session, AIGenerationDraft.TYPE_SITE_CONTENT, payload_json=site_payload)
        validation_reports['site_content_draft_id'] = str(s_draft.id)
    else:
        raise CopilotServiceError('Unsupported session mode.')

    session.status = AICopilotSession.STATUS_GENERATED
    session.save(update_fields=['status', 'updated_at'])
    return validation_reports


def publish_template_from_draft(session: AICopilotSession, template_draft_id, fe_guide_draft_id=None):
    """Publish a template draft into Template* models in current tenant context."""
    if session.mode != AICopilotSession.MODE_TEMPLATE:
        raise CopilotServiceError('Session mode must be template for template publishing.')

    t_draft = get_object_or_404(AIGenerationDraft, id=template_draft_id, session=session, draft_type=AIGenerationDraft.TYPE_TEMPLATE)
    payload = t_draft.payload_json

    validate_payload('template.schema.json', payload)

    with transaction.atomic():
        template = Template.objects.create(
            name=payload['name'],
            slug=payload['slug'],
            description=payload.get('description', ''),
            preview_image_url=payload.get('preview_image_url') or None,
            category=payload.get('category', ''),
            is_active=True,
            is_published=False,
            source_tenant_schema=_current_schema(),
        )

        for p in payload['pages']:
            page = TemplatePage.objects.create(
                template=template,
                title=p['title'],
                slug=p['slug'],
                order=p['order'],
                is_home=p['is_home'],
            )

            for s in p['sections']:
                section = TemplateSection.objects.create(
                    template=template,
                    page=page,
                    type=s['type'],
                    order=s['order'],
                    is_active=s['is_active'],
                )

                for b in s['blocks']:
                    block = TemplateBlock.objects.create(
                        section=section,
                        title=b.get('title', ''),
                        subtitle=b.get('subtitle', ''),
                        description=b.get('description', ''),
                        image_url=b.get('image_url') or None,
                        extra=b.get('extra', {}),
                        order=b['order'],
                    )

                    items = [
                        TemplateListItem(
                            block=block,
                            title=i.get('title', ''),
                            description=i.get('description', ''),
                            icon=i.get('icon', ''),
                            order=i['order'],
                        )
                        for i in b.get('items', [])
                    ]
                    TemplateListItem.objects.bulk_create(items)

        t_draft.is_selected = True
        t_draft.save(update_fields=['is_selected', 'updated_at'])

        if fe_guide_draft_id:
            g_draft = get_object_or_404(
                AIGenerationDraft,
                id=fe_guide_draft_id,
                session=session,
                draft_type=AIGenerationDraft.TYPE_FE_GUIDE,
            )
            g_draft.is_selected = True
            g_draft.save(update_fields=['is_selected', 'updated_at'])

        session.status = AICopilotSession.STATUS_PUBLISHED
        session.save(update_fields=['status', 'updated_at'])

    return template


def publish_site_content_from_draft(session: AICopilotSession, site_content_draft_id, overwrite=False):
    """Publish site content draft into Page/Section/Block/Item models."""
    if session.mode != AICopilotSession.MODE_SITE:
        raise CopilotServiceError('Session mode must be site for site publishing.')

    s_draft = get_object_or_404(
        AIGenerationDraft,
        id=site_content_draft_id,
        session=session,
        draft_type=AIGenerationDraft.TYPE_SITE_CONTENT,
    )
    payload = s_draft.payload_json
    validate_payload('site-content.schema.json', payload)

    with transaction.atomic():
        if overwrite:
            Page.objects.all().delete()
            Section.objects.all().delete()
        elif Page.objects.exists() or Section.objects.exists():
            raise CopilotServiceError('Site content already exists. Pass overwrite=true to replace.')

        for idx, p in enumerate(payload['pages'], start=1):
            page = Page.objects.create(
                title=p['title'],
                slug=p['slug'],
                is_home=p['is_home'],
                is_active=p['is_active'],
                order=p.get('order', idx),
                meta_title=p.get('meta_title', ''),
                meta_description=p.get('meta_description', ''),
            )

            for s in p['sections']:
                section = Section.objects.create(
                    page=page,
                    type=s['type'],
                    order=s['order'],
                    is_active=s['is_active'],
                )

                for b in s['blocks']:
                    block = ContentBlock.objects.create(
                        section=section,
                        title=b.get('title', ''),
                        subtitle=b.get('subtitle', ''),
                        description=b.get('description', ''),
                        image_url=b.get('image_url', ''),
                        extra=b.get('extra', {}),
                        order=b['order'],
                    )

                    items = [
                        ListItem(
                            block=block,
                            title=i.get('title', ''),
                            description=i.get('description', ''),
                            icon=i.get('icon', ''),
                            order=i['order'],
                        )
                        for i in b.get('items', [])
                    ]
                    ListItem.objects.bulk_create(items)

        s_draft.is_selected = True
        s_draft.save(update_fields=['is_selected', 'updated_at'])

        session.status = AICopilotSession.STATUS_PUBLISHED
        session.save(update_fields=['status', 'updated_at'])

    return {'status': 'published'}


def _current_schema():
    from django.db import connection
    return connection.tenant.schema_name


def generate_brainstorm_reply(session: AICopilotSession):
    """Generate one assistant reply based on full session history and llm_mode."""
    adapter = DeepSeekAdapter()
    messages = []
    for msg in session.messages.prefetch_related('attachments').order_by('seq')[:100]:
        content_parts = [{'type': 'text', 'text': msg.content}]
        for att in msg.attachments.all():
            # Native multimodal format for vision mode-compatible chat APIs.
            content_parts.append({
                'type': 'image_url',
                'image_url': {'url': att.url},
            })
            if att.caption:
                content_parts.append({
                    'type': 'text',
                    'text': f'Image note: {att.caption}',
                })

        messages.append({'role': msg.role, 'content': content_parts})

    reply = adapter.brainstorm_reply(
        messages=messages,
        mode=session.mode,
        llm_mode=session.llm_mode,
        llm_model=session.llm_model,
    )
    add_assistant_message(session, reply)
    return reply
