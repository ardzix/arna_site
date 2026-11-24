"""No public proof endpoints; exact-scope operator command and domain route parity."""
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from django.urls import Resolver404, resolve

from core.domain_proof_admission import domain_has_required_proof
from core.domain_proof_scope import PILOT_DOMAIN_ID, PILOT_HOST, PILOT_ORGANIZATION, PILOT_TENANT
from core.models import Domain
from core.views import DomainDetailView, DomainListCreateView


class PilotScopeTests(SimpleTestCase):
    def domain(self, **overrides):
        state = dict(
            pk=PILOT_DOMAIN_ID, domain=PILOT_HOST, role=Domain.ROLE_FRONTEND_CUSTOM,
            status=Domain.STATUS_ACTIVE, verified_at=object(), verification_method="vercel-api-v1",
            tenant=SimpleNamespace(public_id=UUID(PILOT_TENANT), sso_organization_id=PILOT_ORGANIZATION,
                                   is_active=True),
        )
        return SimpleNamespace(**{**state, **overrides})

    def test_no_public_proof_mutation_route(self):
        for action in ("proof", "commit", "activate"):
            with self.assertRaises(Resolver404):
                resolve(f"/domains/{PILOT_DOMAIN_ID}/ownership/{action}/")

    def test_pilot_management_changes_cannot_bypass_operator(self):
        create = DomainListCreateView.post.__wrapped__ if hasattr(DomainListCreateView.post, "__wrapped__") else DomainListCreateView.post
        for spelling in (PILOT_HOST, " ARNATECH.ID. "):
            response = create(object(), SimpleNamespace(data={"domain": spelling, "status": "active"}))
            self.assertEqual(response.status_code, 409)
        view = DomainDetailView()
        target = self.domain(save=Mock(), delete=Mock())
        view._get_domain = Mock(return_value=target)
        self.assertEqual(view.patch(SimpleNamespace(data={"status": "active"}), PILOT_DOMAIN_ID).status_code, 409)
        self.assertEqual(view.delete(SimpleNamespace(), PILOT_DOMAIN_ID).status_code, 409)
        target.save.assert_not_called()
        target.delete.assert_not_called()

    def test_unrelated_patch_and_delete_preserve_legacy_path_even_when_pilot_is_off(self):
        view = DomainDetailView()
        unrelated = self.domain(domain="other.example.test", is_primary=False, save=Mock(), delete=Mock())
        view._get_domain = Mock(return_value=unrelated)
        with patch("core.views.DomainSerializer") as serializer:
            serializer.return_value.data = {"status": "active"}
            r = view.patch(SimpleNamespace(data={"status": "active"}), 999)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(unrelated.status, Domain.STATUS_ACTIVE)
        unrelated.save.assert_called_once_with()
        self.assertEqual(view.delete(SimpleNamespace(), 999).status_code, 204)
        unrelated.delete.assert_called_once_with()

    def test_routing_kill_is_host_scoped_and_never_deletes_audit(self):
        with patch("core.domain_proof_admission.DomainOwnershipAudit.objects") as audit:
            audit.filter.return_value.exists.return_value = True
            with override_settings(DOMAIN_VERCEL_CHAT_ROUTING_ENABLED=False):
                self.assertFalse(domain_has_required_proof(self.domain()))
                self.assertTrue(domain_has_required_proof(self.domain(domain="other.example.test")))
                audit.filter.assert_not_called()
            with override_settings(DOMAIN_VERCEL_CHAT_ROUTING_ENABLED=True):
                self.assertFalse(domain_has_required_proof(self.domain(pk=999)))
                self.assertTrue(domain_has_required_proof(self.domain()))
                audit.filter.assert_called_once()
                audit.filter.return_value.exists.return_value = False
                self.assertFalse(domain_has_required_proof(self.domain()))
            audit.filter.return_value.delete.assert_not_called()


class OperatorCommandTests(SimpleTestCase):
    def test_default_is_dry_run_and_does_not_echo_the_receipt(self):
        output = StringIO()
        with patch("core.management.commands.verify_arnatech_chat_domain.inspect_proof", return_value="synthetic-secret") as inspect, patch(
            "core.management.commands.verify_arnatech_chat_domain.apply_proof"
        ) as apply:
            call_command("verify_arnatech_chat_domain", stdout=output)
            inspect.assert_called_once_with()
            apply.assert_not_called()
        self.assertIn("Dry run", output.getvalue())
        self.assertNotIn("synthetic-secret", output.getvalue())

    def test_command_passes_only_an_operator_owned_private_file_and_no_target_arguments(self):
        output = StringIO()
        with TemporaryDirectory() as tmp, patch(
            "core.management.commands.verify_arnatech_chat_domain.inspect_proof", return_value="synthetic-secret"
        ), patch("core.management.commands.verify_arnatech_chat_domain.apply_proof") as apply:
            path = Path(tmp) / "receipt"
            call_command("verify_arnatech_chat_domain", "--write-receipt", str(path), stdout=output)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            apply.assert_not_called()
            link = Path(tmp) / "link"
            link.symlink_to(path)
            for bad_path in (link, Path(tmp) / "missing"):
                with self.assertRaises(CommandError):
                    call_command("verify_arnatech_chat_domain", "--apply-receipt", str(bad_path), stdout=output)
            path.chmod(0o644)
            with self.assertRaises(CommandError):
                call_command("verify_arnatech_chat_domain", "--apply-receipt", str(path), stdout=output)
            apply.assert_not_called()
            path.chmod(0o600)
            call_command("verify_arnatech_chat_domain", "--apply-receipt", str(path), stdout=output)
            apply.assert_called_once_with("synthetic-secret")
            with self.assertRaises(CommandError):
                call_command("verify_arnatech_chat_domain", "--host", "other.example.test", stdout=output)
        self.assertNotIn("synthetic-secret", output.getvalue())
