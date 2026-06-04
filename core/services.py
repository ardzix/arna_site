"""Module for core.services."""
from django.db import transaction

from core.models import Template
from sites.models import Page, Section, ContentBlock, ListItem


def _current_tenant_id():
    from django.db import connection
    tenant = getattr(connection, "tenant", None)
    return getattr(tenant, "id", None)


def apply_template(tenant_schema: str, template_id: str, overwrite: bool = False):
    """
    Clone template master (public schema) ke tenant schema yang aktif.

    Struktur clone:
      TemplatePage  → Page
      TemplateSection (dalam page) → Section (FK ke page)
      TemplateBlock → ContentBlock
      TemplateListItem → ListItem

    Template lama (tanpa pages) juga didukung: jika template tidak memiliki
    TemplatePage, semua sections di-clone tanpa FK page (backward-compatible).

    Args:
        tenant_schema: nama schema tenant (untuk logging saja — ORM sudah di-switch
                       oleh TenantMainMiddleware).
        template_id:   UUID template yang akan di-clone.
        overwrite:     Jika True, hapus semua Page + orphan Section sebelum clone.

    Raises:
        Template.DoesNotExist: template tidak ditemukan.
        ValueError: konten sudah ada dan overwrite=False.
    """
    template = Template.objects.prefetch_related(
        "pages__sections__blocks__list_items",
        "sections__blocks__list_items",
    ).get(id=template_id)

    with transaction.atomic():
        tenant_id = _current_tenant_id()
        has_content = (
            Page.objects.filter(tenant_id=tenant_id).exists()
            or Section.objects.filter(tenant_id=tenant_id).exists()
        )
        if not overwrite and has_content:
            raise ValueError("Template already applied. Pass overwrite=true to replace.")

        Page.objects.filter(tenant_id=tenant_id).delete()      # CASCADE menghapus sections + blocks + items
        Section.objects.filter(tenant_id=tenant_id).delete()   # Hapus sisa orphan section (tanpa page)

        pages = list(template.pages.all())

        if pages:
            # ── Template dengan multi-page ────────────────────────────────
            for t_page in pages:
                page = Page.objects.create(
                    tenant_id=tenant_id,
                    title=t_page.title,
                    slug=t_page.slug,
                    is_home=t_page.is_home,
                    order=t_page.order,
                    is_active=True,
                    source_template_id=template.id,
                )
                _clone_sections(t_page.sections.all(), page=page, tenant_id=tenant_id)
        else:
            # ── Template lama (flat, tanpa page) ──────────────────────────
            _clone_sections(template.sections.all(), page=None, tenant_id=tenant_id)

    return True


def _clone_sections(template_sections, page, tenant_id):
    """Clone sekumpulan TemplateSection ke tenant schema, opsional dengan page FK."""
    for t_section in template_sections:
        section = Section.objects.create(
            tenant_id=tenant_id,
            page=page,
            template_section_id=t_section.id,
            type=t_section.type,
            order=t_section.order,
            is_active=True,
        )
        for t_block in t_section.blocks.all():
            block = ContentBlock.objects.create(
                section=section,
                template_block_id=t_block.id,
                title=t_block.title or "",
                subtitle=t_block.subtitle or "",
                description=t_block.description or "",
                image_url=t_block.image_url or "",
                extra=t_block.extra or {},
                order=t_block.order,
            )
            items = [
                ListItem(
                    block=block,
                    template_list_item_id=t_item.id,
                    title=t_item.title or "",
                    description=t_item.description or "",
                    icon=t_item.icon or "",
                    order=t_item.order,
                )
                for t_item in t_block.list_items.all()
            ]
            ListItem.objects.bulk_create(items)
