from django.db import transaction
from core.models import Template
from sites.models import Section, ContentBlock, ListItem


def apply_template(tenant_schema: str, template_id: str):
    """
    Clones a master Template (from public schema) into the current Tenant schema.

    Because this is called inside a request hitting a tenant domain
    (e.g., toko-budi.arna.com/tenants/current/apply-template), the TenantMainMiddleware
    has ALREADY locked the database connection to the 'toko-budi' schema.

    Thanks to the TenantSyncRouter:
    - reads from core.Template go to 'public' schema
    - writes to sites.Section go to 'toko-budi' schema
    """
    template = Template.objects.prefetch_related(
        "sections__blocks__list_items"
    ).get(id=template_id)

    with transaction.atomic():
        # Clear existing sites content for this tenant before applying
        Section.objects.all().delete()

        for t_section in template.sections.all():
            section = Section.objects.create(
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

    return True
