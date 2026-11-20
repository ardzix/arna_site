"""Disabled-by-default ownership proof endpoints; no provider writes or public OTP."""
import uuid
from django.conf import settings
from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from core.models import Domain, Tenant, DomainOwnershipAudit
from core.domain_proof_policy import (
    ProofError, binding_for, digest, issue_receipt, read_receipt, receipt_key,
    require_same_state, validate_snapshot,
)
from core.vercel_proof_transport import fetch_verified_evidence


class StrictDomainOwner(BasePermission):
    def has_permission(self, request, view):
        tenant = getattr(connection, "tenant", None)
        user = request.user
        return bool(
            tenant and tenant.schema_name != "public" and tenant.is_active
            and str(getattr(user, "org_id", "")) == str(tenant.sso_organization_id)
            and str(getattr(user, "org_id", ""))
            and (getattr(user, "is_owner", False) is True or "site_admin" in getattr(user, "roles", []))
        )


class ProofThrottle(SimpleRateThrottle):
    scope = "domain_ownership"
    rate = "5/min"

    def get_cache_key(self, request, view):
        identity = str(getattr(request.user, "id", "")) + ":" + str(getattr(request.user, "org_id", ""))
        return self.cache_format % {"scope": self.scope, "ident": digest(identity)}


def snapshot_for(domain, tenant, user):
    if domain.tenant_id != tenant.pk or str(user.org_id) != str(tenant.sso_organization_id):
        raise PermissionDenied("Ownership context changed.")
    if not tenant.is_active or domain.role != Domain.ROLE_FRONTEND_CUSTOM or domain.status != Domain.STATUS_PENDING:
        raise ProofError("pending_custom_domain_required")
    if not domain.verification_token:
        raise ProofError("challenge_required")
    return validate_snapshot({
        "domain_id": domain.pk, "host": domain.domain, "tenant_id": str(tenant.public_id),
        "organization_id": str(tenant.sso_organization_id), "actor_id": str(user.id),
        "challenge_hash": digest(domain.verification_token), "method": domain.verification_method,
    })


class OwnershipBase(APIView):
    # Explicit JWT authentication only; no cookie/CSRF fallback or anonymous receipt bearer.
    from authentication.jwt_backends import ArnaJWTAuthentication
    authentication_classes = [ArnaJWTAuthentication]
    permission_classes = [IsAuthenticated, StrictDomainOwner]
    throttle_classes = [ProofThrottle]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def configuration(self):
        if getattr(settings, "DOMAIN_VERCEL_PROOF_ENABLED", False) is not True:
            raise ProofError("proof_disabled")
        key = getattr(settings, "DOMAIN_VERCEL_RECEIPT_KEY", "")
        receipt_key(key)
        return key, getattr(settings, "DOMAIN_VERCEL_PROOF_BINDINGS", {})

    def current(self, pk, user):
        # Domain and tenant are shared/public tables; always scope by current tenant PK.
        tenant = get_object_or_404(Tenant, pk=connection.tenant.pk)
        domain = get_object_or_404(Domain, pk=pk, tenant_id=tenant.pk)
        return tenant, domain, snapshot_for(domain, tenant, user)


class DomainOwnershipProofView(OwnershipBase):
    def post(self, request, pk):
        if request.data:
            return Response({"error": "empty_body_required"}, status=400)
        try:
            key, bindings = self.configuration()
            _, _, snapshot = self.current(pk, request.user)
            binding = binding_for(snapshot, bindings)
            evidence = fetch_verified_evidence(binding, getattr(settings, "DOMAIN_VERCEL_API_TOKEN", ""))
            receipt = issue_receipt(snapshot, binding, evidence, key)
            return Response({"receipt": receipt, "expires_in": 120, "status": "proof_observed_not_activated"})
        except ProofError as exc:
            return Response({"error": str(exc)}, status=409)


class DomainOwnershipCommitView(OwnershipBase):
    def post(self, request, pk):
        if not isinstance(request.data, dict) or set(request.data) != {"receipt"}:
            return Response({"error": "receipt_only_required"}, status=400)
        try:
            key, bindings = self.configuration()
            claims = read_receipt(request.data["receipt"], key)
            _, _, before = self.current(pk, request.user)
            binding = binding_for(before, bindings)
            # Reject stale/wrong actor/tenant/challenge BEFORE making provider requests.
            if claims["snapshot"] != before or claims["binding"] != binding:
                raise ProofError("ownership_state_changed")
            evidence = fetch_verified_evidence(binding, getattr(settings, "DOMAIN_VERCEL_API_TOKEN", ""))
            require_same_state(claims, before, binding, evidence)
            with transaction.atomic():
                # Consistent order: lock tenant first, then domain. No network under row locks.
                tenant = get_object_or_404(Tenant.objects.select_for_update(), pk=connection.tenant.pk)
                domain = get_object_or_404(Domain.objects.select_for_update(), pk=pk, tenant_id=tenant.pk)
                snapshot = snapshot_for(domain, tenant, request.user)
                current_binding = binding_for(snapshot, getattr(settings, "DOMAIN_VERCEL_PROOF_BINDINGS", {}))
                # Recheck signature/expiry after waiting for locks, not merely before them.
                require_same_state(read_receipt(request.data["receipt"], getattr(settings, "DOMAIN_VERCEL_RECEIPT_KEY", "")), snapshot, current_binding, evidence)
                if getattr(settings, "DOMAIN_VERCEL_PROOF_ENABLED", False) is not True:
                    raise ProofError("proof_disabled")
                DomainOwnershipAudit.objects.create(
                    domain=domain, tenant_public_id=tenant.public_id,
                    organization_id=tenant.sso_organization_id, actor_id=request.user.id,
                    hostname=domain.domain, provider="vercel-api-v1",
                    project_id=binding["project_id"], team_id=binding["team_id"],
                    receipt_hash=digest(request.data["receipt"]), evidence_hash=claims["evidence_hash"],
                )
                domain.status = Domain.STATUS_ACTIVE
                domain.verified_at = timezone.now()
                domain.verification_method = "vercel-api-v1"
                domain.verification_token = uuid.uuid4().hex  # consume original challenge atomically
                domain.save(update_fields=["status", "verified_at", "verification_method", "verification_token"])
            return Response({"status": "active", "proof": "vercel-api-v1"})
        except ProofError as exc:
            return Response({"error": str(exc)}, status=409)
