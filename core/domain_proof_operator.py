"""Local, fixed-target ArnaSite operator workflow. Not importable through an HTTP route."""
from uuid import uuid4, UUID

from django.conf import settings
from django.db import transaction
from django_tenants.utils import schema_context
from django.utils import timezone

from core import domain_proof_scope as scope
from core.models import Domain, Tenant, DomainOwnershipAudit
from core.domain_proof_policy import (
    ProofError, binding_for, digest, issue_receipt, read_receipt, receipt_key,
    require_same_state, validate_snapshot,
)
from core.vercel_proof_transport import fetch_verified_evidence


def configuration():
    if getattr(settings, "DOMAIN_VERCEL_PROOF_ENABLED", False) is not True:
        raise ProofError("proof_disabled")
    actor = getattr(settings, "DOMAIN_VERCEL_PROOF_OPERATOR_ID", "")
    try:
        if str(UUID(actor)) != actor or UUID(actor).int == 0:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ProofError("operator_unconfigured") from None
    key = getattr(settings, "DOMAIN_VERCEL_RECEIPT_KEY", "")
    receipt_key(key)
    bindings = getattr(settings, "DOMAIN_VERCEL_PROOF_BINDINGS", {})
    if not isinstance(bindings, dict) or set(bindings) != {scope.PILOT_TENANT}:
        raise ProofError("pilot_only")
    return actor, key, bindings


def current(*, lock=False):
    # Fixed scope only. Hold no row locks while contacting the fixed Vercel provider.
    tenants, domains = Tenant.objects, Domain.objects
    if lock:
        tenants, domains = tenants.select_for_update(), domains.select_for_update()
    tenant = tenants.filter(public_id=scope.PILOT_TENANT,
                            sso_organization_id=scope.PILOT_ORGANIZATION, is_active=True).first()
    if tenant is None:
        raise ProofError("tenant_binding_changed")
    domain = domains.filter(pk=scope.PILOT_DOMAIN_ID, tenant=tenant).first()
    if domain is None:
        raise ProofError("domain_binding_changed")
    # Bind the exact locked/read tenant instance; no implicit cross-tenant lookup.
    domain.tenant = tenant
    return domain


def snapshot_for(domain, actor):
    if not scope.is_exact_pilot_domain(domain) or domain.status != Domain.STATUS_PENDING:
        raise ProofError("pending_pilot_domain_required")
    if not domain.verification_token:
        raise ProofError("challenge_required")
    return validate_snapshot({
        "domain_id": domain.pk, "host": domain.domain, "tenant_id": str(domain.tenant.public_id),
        "organization_id": str(domain.tenant.sso_organization_id), "actor_id": actor,
        "challenge_hash": digest(domain.verification_token), "method": domain.verification_method,
    })


def inspect_proof():
    actor, key, bindings = configuration()
    with schema_context("public"):
        snapshot = snapshot_for(current(), actor)
    binding = binding_for(snapshot, bindings)
    evidence = fetch_verified_evidence(binding, getattr(settings, "DOMAIN_VERCEL_API_TOKEN", ""))
    return issue_receipt(snapshot, binding, evidence, key)


def apply_proof(receipt):
    actor, key, bindings = configuration()
    claims = read_receipt(receipt, key)
    with schema_context("public"):
        before = snapshot_for(current(), actor)
    binding = binding_for(before, bindings)
    if claims["snapshot"] != before or claims["binding"] != binding:
        raise ProofError("ownership_state_changed")
    evidence = fetch_verified_evidence(binding, getattr(settings, "DOMAIN_VERCEL_API_TOKEN", ""))
    require_same_state(claims, before, binding, evidence)

    with schema_context("public"), transaction.atomic():
        domain = current(lock=True)  # consistent order: tenant, then domain
        live_actor, live_key, live_bindings = configuration()
        snapshot = snapshot_for(domain, live_actor)
        current_binding = binding_for(snapshot, live_bindings)
        require_same_state(read_receipt(receipt, live_key), snapshot, current_binding, evidence)
        DomainOwnershipAudit.objects.create(
            domain=domain, tenant_public_id=domain.tenant.public_id,
            organization_id=domain.tenant.sso_organization_id, actor_id=live_actor,
            hostname=domain.domain, provider="vercel-api-v1", project_id=binding["project_id"],
            team_id=binding["team_id"], receipt_hash=digest(receipt),
            evidence_hash=claims["evidence_hash"],
        )
        domain.status = Domain.STATUS_ACTIVE
        domain.verified_at = timezone.now()
        domain.verification_method = "vercel-api-v1"
        domain.verification_token = uuid4().hex  # atomically consume previous challenge
        domain.save(update_fields=["status", "verified_at", "verification_method", "verification_token"])
