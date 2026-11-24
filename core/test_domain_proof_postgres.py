"""Real disposable PostgreSQL transactions/locks; provider and operator are synthetic."""
import threading
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection, connections, transaction, IntegrityError
from django.db.models.deletion import ProtectedError
from django.test import override_settings
from django.utils import timezone

from core.models import Tenant, Domain, DomainOwnershipAudit
from core.domain_proof_admission import domain_has_required_proof
from core.domain_proof_policy import ProofError, read_receipt, issue_receipt
from core.domain_proof_operator import inspect_proof, apply_proof, issue_challenge

KEY = "synthetic-disposable-postgres-receipt-key-only"


class RealPostgresTests(unittest.TestCase):
    def setUp(self):
        connection.set_schema_to_public()
        cache.clear()
        self.org = str(uuid.uuid4())
        self.user = SimpleNamespace(id=str(uuid.uuid4()), org_id=self.org, roles=["site_admin"],
                                    is_owner=False, is_authenticated=True)
        self.tenant = Tenant(schema_name="synthetic_proof", name="Synthetic proof fixture",
                             slug="proof-" + uuid.uuid4().hex, sso_organization_id=self.org)
        self.tenant.auto_create_schema = False
        self.tenant.save()
        self.domain = Domain.objects.create(
            tenant=self.tenant, domain="proof-" + uuid.uuid4().hex + ".example.test",
            role=Domain.ROLE_FRONTEND_CUSTOM, status=Domain.STATUS_PENDING,
            verification_token=uuid.uuid4().hex, verification_method="txt", is_primary=False)
        self.evidence = {"provider": "https-origin-v1", "host": self.domain.domain,
                         "path": "/.well-known/arnatech-bnk-verification/",
                         "challenge_hash": "1" * 64, "tls_verified": True}
        self.scope = patch.multiple("core.domain_proof_scope", PILOT_HOST=self.domain.domain,
                                    PILOT_DOMAIN_ID=self.domain.pk, PILOT_TENANT=str(self.tenant.public_id),
                                    PILOT_ORGANIZATION=self.org)
        self.scope.start()
        self.addCleanup(self.scope.stop)
        self.settings = override_settings(
            DOMAIN_HTTPS_PROOF_ENABLED=True, DOMAIN_HTTPS_RECEIPT_KEY=KEY,
            DOMAIN_HTTPS_PROOF_OPERATOR_ID=self.user.id, DOMAIN_HTTPS_CHAT_ROUTING_ENABLED=True)
        self.settings.enable()
        self.manifest = issue_challenge()["manifest"]
        self.addCleanup(self.settings.disable)
        self.provider = patch("core.domain_proof_operator.fetch_https_evidence", return_value=self.evidence).start()
        self.addCleanup(patch.stopall)

    def proof(self):
        return inspect_proof(self.manifest)

    def commit(self, receipt):
        try:
            apply_proof(receipt, self.manifest)
            return SimpleNamespace(status_code=200)
        except ProofError:
            return SimpleNamespace(status_code=409)

    def persisted(self):
        self.domain.refresh_from_db()
        return DomainOwnershipAudit.objects.filter(domain=self.domain)

    def thread_commit(self, receipt, results, errors, name=None):
        try:
            connections.close_all()
            connection.set_schema_to_public()
            if name:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('application_name', %s, false)", [name])
            results.append(self.commit(receipt).status_code)
        except BaseException as error:
            errors.append(type(error).__name__ + ": " + str(error))
        finally:
            connections.close_all()

    def test_real_commit_persists_audit_and_consumes_challenge(self):
        receipt = self.proof()
        original = self.domain.verification_token
        self.assertEqual(self.commit(receipt).status_code, 200)
        audit = self.persisted().get()
        self.assertEqual(self.domain.status, Domain.STATUS_ACTIVE)
        self.assertNotEqual(self.domain.verification_token, original)
        self.assertTrue(domain_has_required_proof(self.domain))
        self.assertEqual(str(audit.tenant_public_id), str(self.tenant.public_id))
        self.assertNotIn(receipt, str(audit.__dict__))
        self.assertEqual(audit.hostname, self.domain.domain)

    def test_real_audit_and_activation_rollback_together_on_save_failure(self):
        receipt = self.proof()
        original = self.domain.verification_token
        with patch.object(Domain, "save", side_effect=IntegrityError("synthetic commit failure")):
            with self.assertRaises(IntegrityError):
                self.commit(receipt)
        self.assertEqual(self.persisted().count(), 0)
        self.assertEqual(self.domain.status, Domain.STATUS_PENDING)
        self.assertEqual(self.domain.verification_token, original)
        self.assertIsNone(self.domain.verified_at)

    def test_two_real_concurrent_commits_accept_exactly_one_receipt(self):
        receipt = self.proof()
        barrier = threading.Barrier(2, timeout=4)
        def observed(*args):
            self.assertFalse(connection.in_atomic_block, "provider request under database lock")
            barrier.wait()
            return self.evidence
        self.provider.side_effect = observed
        results, errors = [], []
        workers = [threading.Thread(target=self.thread_commit, args=(receipt, results, errors), daemon=True) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(10)
            self.assertFalse(worker.is_alive(), "worker exceeded bounded join")
        self.assertEqual(errors, [])
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(self.persisted().count(), 1)
        self.assertEqual(self.domain.status, Domain.STATUS_ACTIVE)

    def test_replay_is_rejected_from_persisted_consumed_state(self):
        receipt = self.proof()
        self.assertEqual(self.commit(receipt).status_code, 200)
        self.assertEqual(self.commit(receipt).status_code, 409)
        self.assertEqual(self.persisted().count(), 1)

    def test_owner_change_before_row_lock_fails_closed(self):
        receipt = self.proof()
        def changed(*args):
            Tenant.objects.filter(pk=self.tenant.pk).update(sso_organization_id=str(uuid.uuid4()))
            return self.evidence
        self.provider.side_effect = changed
        self.assertEqual(self.commit(receipt).status_code, 409)
        self.assertEqual(self.persisted().count(), 0)
        self.assertEqual(self.domain.status, Domain.STATUS_PENDING)

    def test_domain_change_before_row_lock_fails_closed(self):
        receipt = self.proof()
        def changed(*args):
            Domain.objects.filter(pk=self.domain.pk).update(domain="changed-" + uuid.uuid4().hex + ".example.test")
            return self.evidence
        self.provider.side_effect = changed
        self.assertEqual(self.commit(receipt).status_code, 409)
        self.assertEqual(self.persisted().count(), 0)
        self.assertEqual(self.domain.status, Domain.STATUS_PENDING)

    def test_expiry_is_checked_after_an_observed_real_postgres_lock_wait(self):
        original_receipt = self.proof()
        claims = read_receipt(original_receipt, KEY)
        receipt = issue_receipt(claims["snapshot"], claims["binding"], self.evidence, KEY, now=1000)
        clock, results, errors = [1119], [], []
        provider_seen = threading.Event()
        def observed(*args):
            provider_seen.set()
            return self.evidence
        def clock_read(value, key):
            return read_receipt(value, key, now=clock[0])
        self.provider.side_effect = observed
        with patch("core.domain_proof_operator.read_commit_receipt", side_effect=clock_read):
            with transaction.atomic():
                Tenant.objects.select_for_update().get(pk=self.tenant.pk)
                worker = threading.Thread(target=self.thread_commit,
                    args=(receipt, results, errors, "proof-expiry-worker"), daemon=True)
                worker.start()
                self.assertTrue(provider_seen.wait(2))
                deadline = time.monotonic() + 2
                observed_lock = False
                while time.monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE application_name=%s AND wait_event_type='Lock')",
                                       ["proof-expiry-worker"])
                        observed_lock = cursor.fetchone()[0]
                    if observed_lock:
                        break
                    time.sleep(0.05)
                self.assertTrue(observed_lock, "test did not observe a PostgreSQL lock wait")
                clock[0] = 1120  # exact 120-second expiry before releasing the real row lock
            worker.join(10)
            self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, [409])
        self.assertEqual(self.persisted().count(), 0)
        self.assertEqual(self.domain.status, Domain.STATUS_PENDING)

    def test_provider_failure_has_no_persisted_effect(self):
        receipt = self.proof()
        self.provider.side_effect = ProofError("provider_unavailable")
        self.assertEqual(self.commit(receipt).status_code, 409)
        self.assertEqual(self.persisted().count(), 0)
        self.assertEqual(self.domain.status, Domain.STATUS_PENDING)

    def test_tampered_receipt_has_no_provider_or_database_effect(self):
        receipt = self.proof()
        self.provider.reset_mock()
        receipt = receipt[:-1] + ("0" if receipt[-1] != "0" else "1")
        self.assertEqual(self.commit(receipt).status_code, 409)
        self.provider.assert_not_called()
        self.assertEqual(self.persisted().count(), 0)

    def test_other_tenant_in_same_org_cannot_consume_receipt(self):
        receipt = self.proof()
        other = Tenant(schema_name="synthetic_other", name="Synthetic other fixture",
                       slug="other-" + uuid.uuid4().hex, sso_organization_id=self.org)
        other.auto_create_schema = False
        other.save()
        Domain.objects.filter(pk=self.domain.pk).update(tenant=other)
        self.assertEqual(self.commit(receipt).status_code, 409)
        self.assertEqual(self.persisted().count(), 0)

    def test_bare_status_and_timestamp_without_matching_audit_do_not_admit(self):
        Domain.objects.filter(pk=self.domain.pk).update(
            status=Domain.STATUS_ACTIVE, verified_at=timezone.now(), verification_method="https-origin-v1")
        self.persisted()
        self.assertFalse(domain_has_required_proof(self.domain))

    def test_disabled_feature_retains_forward_schema_and_audit(self):
        receipt = self.proof()
        self.assertEqual(self.commit(receipt).status_code, 200)
        audit = self.persisted().get()
        with override_settings(DOMAIN_HTTPS_PROOF_ENABLED=False):
            self.assertEqual(self.commit(receipt).status_code, 409)
            self.assertTrue(domain_has_required_proof(self.domain))
        with override_settings(DOMAIN_HTTPS_CHAT_ROUTING_ENABLED=False):
            self.assertFalse(domain_has_required_proof(self.domain))
        self.assertTrue(DomainOwnershipAudit.objects.filter(pk=audit.pk).exists())
        self.assertEqual(self.persisted().count(), 1)

    def test_audit_prevents_accidental_domain_delete(self):
        receipt = self.proof()
        self.assertEqual(self.commit(receipt).status_code, 200)
        with self.assertRaises(ProtectedError):
            Domain.objects.filter(pk=self.domain.pk).delete()
        self.assertEqual(self.persisted().count(), 1)
