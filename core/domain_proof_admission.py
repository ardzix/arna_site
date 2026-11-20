"""Require an audit for new/pending custom domains even after a bare status flip."""
from core.models import Domain, DomainOwnershipAudit


def domain_has_required_proof(domain):
    if domain.role != Domain.ROLE_FRONTEND_CUSTOM or not domain.ownership_proof_required:
        return True  # Existing active legacy domains are explicitly grandfathered by migration.
    if domain.status != Domain.STATUS_ACTIVE or not domain.verified_at or domain.verification_method != "vercel-api-v1":
        return False
    return DomainOwnershipAudit.objects.filter(
        domain_id=domain.pk, hostname=domain.domain,
        tenant_public_id=domain.tenant.public_id,
        organization_id=domain.tenant.sso_organization_id, provider="vercel-api-v1",
    ).exists()
