"""Domain audit admission is only for Arnatech pilot chat, never unrelated CMS/CRM."""
from django.conf import settings

from core.domain_proof_scope import is_exact_pilot_domain, is_pilot_host
from core.models import Domain, DomainOwnershipAudit


def domain_has_required_proof(domain):
    if not is_pilot_host(domain.domain):
        return True
    if getattr(settings, "DOMAIN_VERCEL_CHAT_ROUTING_ENABLED", False) is not True:
        return False
    if not is_exact_pilot_domain(domain):
        return False
    if domain.status != Domain.STATUS_ACTIVE or not domain.verified_at or domain.verification_method != "vercel-api-v1":
        return False
    return DomainOwnershipAudit.objects.filter(
        domain_id=domain.pk, hostname=domain.domain,
        tenant_public_id=domain.tenant.public_id,
        organization_id=domain.tenant.sso_organization_id, provider="vercel-api-v1",
    ).exists()
