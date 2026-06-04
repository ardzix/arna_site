from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.models import Tenant
from core.services import apply_template
from sites.models import Page, Section


class Command(BaseCommand):
    help = (
        "Repair shared-schema site content by assigning existing unscoped content "
        "to one tenant and applying a template to another tenant."
    )

    def add_arguments(self, parser):
        parser.add_argument("--claim-unscoped-to", required=True, help="Tenant slug that owns existing unscoped pages.")
        parser.add_argument("--apply-template-to", required=True, help="Tenant slug that should receive a fresh template.")
        parser.add_argument("--template-id", required=True, help="Template UUID to apply to --apply-template-to.")
        parser.add_argument("--apply", action="store_true", help="Persist changes. Without this, only prints what would happen.")

    def handle(self, *args, **options):
        claim_slug = options["claim_unscoped_to"]
        target_slug = options["apply_template_to"]
        template_id = options["template_id"]
        should_apply = options["apply"]

        claim_tenant = Tenant.objects.filter(slug=claim_slug).first()
        target_tenant = Tenant.objects.filter(slug=target_slug).first()
        if not claim_tenant:
            raise CommandError(f"Tenant not found: {claim_slug}")
        if not target_tenant:
            raise CommandError(f"Tenant not found: {target_slug}")
        if claim_tenant.schema_name != target_tenant.schema_name:
            raise CommandError("This repair command is intended for tenants sharing one schema.")

        connection.set_tenant(claim_tenant)
        unscoped_pages = Page.objects.filter(tenant_id__isnull=True).count()
        unscoped_sections = Section.objects.filter(tenant_id__isnull=True).count()
        target_pages = Page.objects.filter(tenant_id=target_tenant.id).count()

        self.stdout.write(
            f"schema={claim_tenant.schema_name} unscoped_pages={unscoped_pages} "
            f"unscoped_sections={unscoped_sections} target_existing_pages={target_pages}"
        )

        if not should_apply:
            self.stdout.write(self.style.WARNING("Dry run only. Re-run with --apply to persist changes."))
            return

        with transaction.atomic():
            Page.objects.filter(tenant_id__isnull=True).update(tenant_id=claim_tenant.id)
            Section.objects.filter(tenant_id__isnull=True).update(tenant_id=claim_tenant.id)

        connection.set_tenant(target_tenant)
        apply_template(target_tenant.schema_name, template_id, overwrite=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Assigned unscoped content to {claim_slug} and applied template {template_id} to {target_slug}."
            )
        )
