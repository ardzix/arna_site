"""DRF endpoint tests with synthetic provider and mocked row locks; NOT DB concurrency proof."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate
from core.models import Domain, Tenant
from core.domain_proof_policy import ProofError, read_receipt
from core.domain_proof_views import DomainOwnershipProofView, DomainOwnershipCommitView
from core.domain_proof_admission import domain_has_required_proof
from core.test_domain_proof_policy import KEY, SNAPSHOT, BINDING, PROJECT, DOMAIN
from core.domain_proof_policy import verified_evidence


@override_settings(
    DOMAIN_VERCEL_PROOF_ENABLED=True, DOMAIN_VERCEL_RECEIPT_KEY=KEY,
    DOMAIN_VERCEL_API_TOKEN="synthetic-not-a-provider-token",
    DOMAIN_VERCEL_PROOF_BINDINGS={SNAPSHOT["tenant_id"]: BINDING},
)
class OwnershipAPITests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.tenant = SimpleNamespace(pk=85, schema_name="synthetic", public_id=UUID(SNAPSHOT["tenant_id"]),
                                      sso_organization_id=SNAPSHOT["organization_id"], is_active=True)
        self.user = SimpleNamespace(id=SNAPSHOT["actor_id"], org_id=SNAPSHOT["organization_id"],
                                    roles=["site_admin"], is_owner=False, is_authenticated=True)
        self.domain = SimpleNamespace(pk=174, domain=BINDING["host"], tenant_id=85, tenant=self.tenant,
                                      role=Domain.ROLE_FRONTEND_CUSTOM, status=Domain.STATUS_PENDING,
                                      verification_token="synthetic-challenge", verification_method="txt",
                                      verified_at=None, ownership_proof_required=True, save=Mock())
        self.evidence = verified_evidence(PROJECT, DOMAIN, BINDING)
        self.provider = patch("core.domain_proof_views.fetch_verified_evidence", return_value=self.evidence).start()
        patch("core.domain_proof_views.connection", SimpleNamespace(tenant=self.tenant)).start()
        patch("core.domain_proof_views.transaction.atomic", return_value=nullcontext()).start()
        self.tenant_manager = patch("core.domain_proof_views.Tenant.objects").start()
        self.domain_manager = patch("core.domain_proof_views.Domain.objects").start()
        self.audit_manager = patch("core.domain_proof_views.DomainOwnershipAudit.objects").start()
        self.lookup = patch("core.domain_proof_views.get_object_or_404", side_effect=self.lookup_row).start()
        self.addCleanup(patch.stopall)

    def lookup_row(self, model, **filters):
        if model is Tenant or model is self.tenant_manager.select_for_update.return_value:
            self.assertEqual(filters, {"pk": 85})
            return self.tenant
        self.assertEqual(filters, {"pk": 174, "tenant_id": 85})
        return self.domain

    def call(self, view, data, user=True):
        request = APIRequestFactory().post("/domains/174/ownership/", data, format="json")
        if user:
            force_authenticate(request, user=self.user)
        return view.as_view()(request, pk=174)

    def proof(self):
        response = self.call(DomainOwnershipProofView, {})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["receipt"]

    def test_proof_does_not_activate_or_save(self):
        receipt = self.proof()
        self.assertEqual(read_receipt(receipt, KEY)["snapshot"], SNAPSHOT)
        self.domain.save.assert_not_called()
        self.audit_manager.create.assert_not_called()

    def test_valid_commit_consumes_challenge_and_records_nonsecret_audit(self):
        receipt = self.proof()
        response = self.call(DomainOwnershipCommitView, {"receipt": receipt})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.domain.status, Domain.STATUS_ACTIVE)
        self.assertNotEqual(self.domain.verification_token, "synthetic-challenge")
        self.domain.save.assert_called_once()
        self.audit_manager.create.assert_called_once()
        self.assertNotIn(receipt, str(self.audit_manager.create.call_args))
        self.assertEqual(self.provider.call_count, 2)

    def test_replay_cannot_save_or_call_provider_again(self):
        receipt = self.proof()
        self.assertEqual(self.call(DomainOwnershipCommitView, {"receipt": receipt}).status_code, 200)
        self.assertEqual(self.call(DomainOwnershipCommitView, {"receipt": receipt}).status_code, 409)
        self.assertEqual(self.domain.save.call_count, 1)
        self.assertEqual(self.provider.call_count, 2)

    def test_invalid_signature_fails_before_provider_or_database(self):
        response = self.call(DomainOwnershipCommitView, {"receipt": "invalid"})
        self.assertEqual(response.status_code, 409)
        self.provider.assert_not_called()
        self.lookup.assert_not_called()
        self.domain.save.assert_not_called()

    def test_anonymous_denied(self):
        self.assertEqual(self.call(DomainOwnershipProofView, {}, user=False).status_code, 401)
        self.provider.assert_not_called()

    def test_non_admin_and_wrong_org_denied_without_schema_fallback(self):
        for roles, org in (([], self.user.org_id), (["site_admin"], ""), (["site_admin"], "other-org")):
            self.user.roles, self.user.org_id = roles, org
            self.assertEqual(self.call(DomainOwnershipProofView, {}).status_code, 403)
        self.provider.assert_not_called()

    def test_owner_role_supported(self):
        self.user.roles, self.user.is_owner = [], True
        self.proof()

    @override_settings(DOMAIN_VERCEL_PROOF_ENABLED=False)
    def test_disabled_has_no_provider_or_database_activity(self):
        self.assertEqual(self.call(DomainOwnershipProofView, {}).status_code, 409)
        self.lookup.assert_not_called()
        self.provider.assert_not_called()

    @override_settings(DOMAIN_VERCEL_RECEIPT_KEY="")
    def test_no_secret_key_fallback(self):
        self.assertEqual(self.call(DomainOwnershipProofView, {}).status_code, 409)
        self.provider.assert_not_called()

    def test_client_cannot_submit_provider_json_or_ownership_fields(self):
        for body in ({"verified": True}, {"status": "active"}, {"host": "other.test"}, {"project_id": "prj_other"}):
            self.assertEqual(self.call(DomainOwnershipProofView, body).status_code, 400)
        self.provider.assert_not_called()

    def test_commit_rejects_extra_fields(self):
        self.assertEqual(self.call(DomainOwnershipCommitView, {"receipt": "x", "status": "active"}).status_code, 400)
        self.provider.assert_not_called()

    def test_provider_failure_never_activates(self):
        receipt = self.proof()
        self.provider.side_effect = ProofError("provider_unavailable")
        self.assertEqual(self.call(DomainOwnershipCommitView, {"receipt": receipt}).status_code, 409)
        self.domain.save.assert_not_called()
        self.audit_manager.create.assert_not_called()

    def test_changed_challenge_rejected_before_provider(self):
        receipt = self.proof()
        self.domain.verification_token = "rotated"
        self.assertEqual(self.call(DomainOwnershipCommitView, {"receipt": receipt}).status_code, 409)
        self.assertEqual(self.provider.call_count, 1)
        self.domain.save.assert_not_called()

    def test_different_admin_cannot_consume_receipt(self):
        receipt = self.proof()
        self.user.id = "be08e7ab-62b2-4425-89b2-830d710a7c97"
        self.assertEqual(self.call(DomainOwnershipCommitView, {"receipt": receipt}).status_code, 409)
        self.assertEqual(self.provider.call_count, 1)

    def test_owner_changes_while_waiting_for_lock(self):
        receipt = self.proof()
        def lookup(model, **filters):
            if model is self.tenant_manager.select_for_update.return_value:
                self.tenant.sso_organization_id = "35c1bf82-5eac-4507-a5d7-b1e271fdbb9f"
            return self.lookup_row(model, **filters)
        self.lookup.side_effect = lookup
        self.assertEqual(self.call(DomainOwnershipCommitView, {"receipt": receipt}).status_code, 403)
        self.domain.save.assert_not_called()
        self.audit_manager.create.assert_not_called()

    def test_hostname_changes_while_waiting_for_lock(self):
        receipt = self.proof()
        def lookup(model, **filters):
            if model is self.domain_manager.select_for_update.return_value:
                self.domain.domain = "other.test"
            return self.lookup_row(model, **filters)
        self.lookup.side_effect = lookup
        self.assertEqual(self.call(DomainOwnershipCommitView, {"receipt": receipt}).status_code, 409)
        self.domain.save.assert_not_called()

    def test_expired_receipt_rechecked_after_lock(self):
        receipt = self.proof()
        from core.domain_proof_policy import read_receipt as real_read
        with patch("core.domain_proof_views.read_receipt", side_effect=[real_read(receipt, KEY), ProofError("invalid_or_expired_receipt")]):
            self.assertEqual(self.call(DomainOwnershipCommitView, {"receipt": receipt}).status_code, 409)
        self.domain.save.assert_not_called()
        self.audit_manager.create.assert_not_called()

    def test_bare_status_and_timestamp_without_audit_do_not_admit_new_domain(self):
        self.domain.status, self.domain.verified_at = Domain.STATUS_ACTIVE, object()
        self.assertFalse(domain_has_required_proof(self.domain))
        self.domain.verification_method = "vercel-api-v1"
        with patch("core.domain_proof_admission.DomainOwnershipAudit.objects") as audit:
            audit.filter.return_value.exists.return_value = False
            self.assertFalse(domain_has_required_proof(self.domain))
            audit.filter.return_value.exists.return_value = True
            self.assertTrue(domain_has_required_proof(self.domain))
            audit.filter.assert_called_with(domain_id=174, hostname=BINDING["host"],
                tenant_public_id=self.tenant.public_id, organization_id=self.tenant.sso_organization_id,
                provider="vercel-api-v1")

    def test_existing_active_legacy_domain_remains_compatible(self):
        self.domain.ownership_proof_required = False
        self.assertTrue(domain_has_required_proof(self.domain))
