"""Local fixed-target Arnatech origin operator. No browser or public-write authority."""
import re
from secrets import token_hex
import time
from uuid import uuid4, UUID

from django.conf import settings
from django.db import transaction
from django_tenants.utils import schema_context
from django.utils import timezone

from core import domain_proof_scope as scope
from core.models import Domain, Tenant, DomainOwnershipAudit
from core.domain_proof_policy import (
    CHALLENGE_SALT, CHALLENGE_TTL, ProofError, digest, issue_receipt, read_receipt, receipt_key,
    require_same_state, validate_snapshot,
)
from core.https_proof_transport import fetch_https_evidence

CHALLENGE_FORMAT = re.compile(r"arnatech-bnk-https-v1 [0-9a-f]{64} ([0-9]{10})")


def configuration():
    if getattr(settings, "DOMAIN_HTTPS_PROOF_ENABLED", False) is not True:
        raise ProofError("proof_disabled")
    actor = getattr(settings, "DOMAIN_HTTPS_PROOF_OPERATOR_ID", "")
    try:
        if str(UUID(actor)) != actor or UUID(actor).int == 0:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ProofError("operator_unconfigured") from None
    key = getattr(settings, "DOMAIN_HTTPS_RECEIPT_KEY", "")
    receipt_key(key)
    return actor, key


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



def issue_challenge():
    actor, key = configuration()
    with schema_context("public"):
        snapshot = snapshot_for(current(), actor)
    now = int(time.time())
    value = f"arnatech-bnk-https-v1 {token_hex(32)} {now + CHALLENGE_TTL}"
    # Separate signature purpose: a challenge cannot be submitted as an apply receipt.
    manifest = issue_receipt(snapshot, {"publish_value": value}, {"kind": "pending_origin_proof"},
                             key, now=now, ttl=CHALLENGE_TTL, salt=CHALLENGE_SALT)
    return {"manifest": manifest, "publish_value": value}


def read_challenge(manifest, key, snapshot):
    claims = read_receipt(manifest, key, ttl=CHALLENGE_TTL, salt=CHALLENGE_SALT)
    binding = claims["binding"]
    if claims["snapshot"] != snapshot or not isinstance(binding, dict) or set(binding) != {"publish_value"}:
        raise ProofError("challenge_scope_changed")
    value = binding["publish_value"]
    match = CHALLENGE_FORMAT.fullmatch(value) if isinstance(value, str) else None
    if not match or int(match[1]) != claims["exp"]:
        raise ProofError("invalid_challenge_manifest")
    return value


def read_commit_receipt(receipt, key):
    return read_receipt(receipt, key)


def inspect_proof(manifest):
    actor, key = configuration()
    with schema_context("public"):
        snapshot = snapshot_for(current(), actor)
    expected = read_challenge(manifest, key, snapshot)
    evidence = fetch_https_evidence(expected)
    read_challenge(manifest, key, snapshot)  # never issue a receipt for an expired proof
    return issue_receipt(snapshot, {"manifest_hash": digest(manifest)}, evidence, key)


def apply_proof(receipt, manifest):
    actor, key = configuration()
    claims = read_commit_receipt(receipt, key)
    with schema_context("public"):
        before = snapshot_for(current(), actor)
    binding = {"manifest_hash": digest(manifest)}
    if claims["snapshot"] != before or claims["binding"] != binding:
        raise ProofError("ownership_state_changed")
    expected = read_challenge(manifest, key, before)
    evidence = fetch_https_evidence(expected)
    require_same_state(claims, before, binding, evidence)

    with schema_context("public"), transaction.atomic():
        domain = current(lock=True)
        live_actor, live_key = configuration()
        snapshot = snapshot_for(domain, live_actor)
        read_challenge(manifest, live_key, snapshot)
        require_same_state(read_commit_receipt(receipt, live_key), snapshot, binding, evidence)
        DomainOwnershipAudit.objects.create(
            domain=domain, tenant_public_id=domain.tenant.public_id,
            organization_id=domain.tenant.sso_organization_id, actor_id=live_actor,
            hostname=domain.domain, provider="https-origin-v1", receipt_hash=digest(receipt),
            evidence_hash=claims["evidence_hash"],
        )
        domain.status = Domain.STATUS_ACTIVE
        domain.verified_at = timezone.now()
        domain.verification_method = "https-origin-v1"
        domain.verification_token = uuid4().hex
        domain.save(update_fields=["status", "verified_at", "verification_method", "verification_token"])
