"""Compare-and-set a website's CRM inbox without transferring its website or history."""
import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_tenants.utils import schema_context

from core.models import Domain, Tenant


class Command(BaseCommand):
    help = "Set same-organization CRM routing for verified domains; dry-run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("--organization", required=True)
        parser.add_argument("--website-tenant", required=True)
        parser.add_argument("--expected-current-tenant", required=True)
        destination = parser.add_mutually_exclusive_group(required=True)
        destination.add_argument("--target-tenant")
        destination.add_argument("--clear", action="store_true")
        parser.add_argument("--host", action="append", required=True)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            org = str(UUID(options["organization"]))
            owner_id = UUID(options["website_tenant"])
            expected = UUID(options["expected_current_tenant"])
            target_id = UUID(options["target_tenant"]) if options["target_tenant"] else None
        except (ValueError, TypeError):
            raise CommandError("Valid organization and tenant UUIDs are required.") from None
        hosts = set(options["host"])
        with schema_context("public"), transaction.atomic():
            try:
                owner = Tenant.objects.select_for_update().get(
                    public_id=owner_id, sso_organization_id=org, is_active=True,
                )
                target = Tenant.objects.select_for_update().get(
                    public_id=target_id, sso_organization_id=org, is_active=True,
                ) if target_id else None
            except Tenant.DoesNotExist:
                raise CommandError("Website owner and CRM destination must be active in this organization.") from None
            rows = list(Domain.objects.select_for_update(of=("self",)).select_related("tenant", "crm_tenant").filter(
                tenant=owner, domain__in=hosts,
                role__in=[Domain.ROLE_FRONTEND_CUSTOM, Domain.ROLE_FRONTEND_DEFAULT],
                status=Domain.STATUS_ACTIVE, verified_at__isnull=False,
            ).order_by("domain"))
            if len(rows) != len(hosts):
                raise CommandError("Every exact hostname must be a verified domain of the selected website tenant.")
            bindings = []
            for row in rows:
                current = row.crm_tenant or row.tenant
                # Retrying an already-applied request is harmless and does not mutate history.
                desired = target or owner
                if current.public_id not in {expected, desired.public_id}:
                    raise CommandError("Current CRM destination changed; no domains were updated.")
                bindings.append({"domain": row.domain, "website_tenant": str(owner.public_id),
                                 "previous_crm_tenant": str(current.public_id),
                                 "crm_tenant": str(desired.public_id)})
                row.crm_tenant = target
                row.clean()
            if options["apply"]:
                for row in rows:
                    Domain.objects.filter(pk=row.pk, tenant=owner).update(crm_tenant=target)
            self.stdout.write(json.dumps({"applied": options["apply"], "organization_id": org, "bindings": bindings}))
