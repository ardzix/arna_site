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

from core.domain_proof_admission import domain_has_required_proof
from core.domain_proof_scope import PILOT_DOMAIN_ID, PILOT_HOST, PILOT_ORGANIZATION, PILOT_TENANT
from core.models import Domain
from core.domain_proof_scope import is_pilot_host


class PilotScopeTests(SimpleTestCase):
    def domain(self, **overrides):
        state = dict(
            pk=PILOT_DOMAIN_ID, domain=PILOT_HOST, role=Domain.ROLE_FRONTEND_CUSTOM,
            status=Domain.STATUS_ACTIVE, verified_at=object(), verification_method="https-origin-v1",
            tenant=SimpleNamespace(public_id=UUID(PILOT_TENANT), sso_organization_id=PILOT_ORGANIZATION,
                                   is_active=True),
        )
        return SimpleNamespace(**{**state, **overrides})

    def actual_method(self, class_name, method_name):
        # Execute reviewed method bodies without initializing the unrelated Swagger dependency.
        import ast
        from copy import deepcopy
        from django.utils import timezone
        from rest_framework.response import Response
        tree = ast.parse(Path(__file__).with_name("views.py").read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
        method = deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name))
        method.decorator_list = []
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        serializer = Mock(return_value=SimpleNamespace(data={"status": "active"}))
        namespace = {"Domain": Domain, "Response": Response, "DomainSerializer": serializer,
                     "is_pilot_host": is_pilot_host, "timezone": timezone}
        exec(compile(module, "core/views.py:reviewed-method", "exec"), namespace)
        return namespace[method_name]

    def test_no_public_proof_mutation_route(self):
        import ast
        tree = ast.parse(Path(__file__).with_name("domain_urls.py").read_text())
        paths = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call) and
                 getattr(n.func, "id", "") == "path" and isinstance(n.args[0], ast.Constant)}
        self.assertEqual(paths, {"website-context/", "resolve/", "", "<int:pk>/"})
        self.assertFalse(Path(__file__).with_name("domain_proof_views.py").exists())

    def test_pilot_management_changes_cannot_bypass_operator(self):
        create = self.actual_method("DomainListCreateView", "post")
        patch_domain = self.actual_method("DomainDetailView", "patch")
        delete = self.actual_method("DomainDetailView", "delete")
        for spelling in (PILOT_HOST, " ARNATECH.ID. "):
            response = create(object(), SimpleNamespace(data={"domain": spelling, "status": "active"}))
            self.assertEqual(response.status_code, 409)
        target = self.domain(save=Mock(), delete=Mock())
        view = SimpleNamespace(_get_domain=Mock(return_value=target))
        self.assertEqual(patch_domain(view, SimpleNamespace(data={"status": "active"}), PILOT_DOMAIN_ID).status_code, 409)
        self.assertEqual(delete(view, SimpleNamespace(), PILOT_DOMAIN_ID).status_code, 409)
        target.save.assert_not_called()
        target.delete.assert_not_called()

    def test_unrelated_patch_and_delete_preserve_legacy_path_even_when_pilot_is_off(self):
        patch_domain = self.actual_method("DomainDetailView", "patch")
        delete = self.actual_method("DomainDetailView", "delete")
        unrelated = self.domain(domain="other.example.test", is_primary=False, save=Mock(), delete=Mock())
        view = SimpleNamespace(_get_domain=Mock(return_value=unrelated))
        r = patch_domain(view, SimpleNamespace(data={"status": "active"}), 999)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(unrelated.status, Domain.STATUS_ACTIVE)
        unrelated.save.assert_called_once_with()
        self.assertEqual(delete(view, SimpleNamespace(), 999).status_code, 204)
        unrelated.delete.assert_called_once_with()

    def test_routing_kill_is_host_scoped_and_never_deletes_audit(self):
        with patch("core.domain_proof_admission.DomainOwnershipAudit.objects") as audit:
            audit.filter.return_value.exists.return_value = True
            with override_settings(DOMAIN_HTTPS_CHAT_ROUTING_ENABLED=False):
                self.assertFalse(domain_has_required_proof(self.domain()))
                self.assertTrue(domain_has_required_proof(self.domain(domain="other.example.test")))
                audit.filter.assert_not_called()
            with override_settings(DOMAIN_HTTPS_CHAT_ROUTING_ENABLED=True):
                self.assertFalse(domain_has_required_proof(self.domain(pk=999)))
                self.assertTrue(domain_has_required_proof(self.domain()))
                audit.filter.assert_called_once()
                audit.filter.return_value.exists.return_value = False
                self.assertFalse(domain_has_required_proof(self.domain()))
            audit.filter.return_value.delete.assert_not_called()


class OperatorCommandTests(SimpleTestCase):
    def test_challenge_issuance_is_local_and_dry_run_never_applies_or_echoes_material(self):
        output = StringIO()
        root = "core.management.commands.verify_arnatech_chat_domain."
        with TemporaryDirectory() as tmp, patch(root + "issue_challenge",
            return_value={"manifest": "synthetic-manifest", "publish_value": "synthetic-value"}) as issue, patch(
            root + "inspect_proof", return_value="synthetic-receipt"
        ) as inspect, patch(root + "apply_proof") as apply:
            challenge = Path(tmp) / "challenge"
            receipt = Path(tmp) / "receipt"
            call_command("verify_arnatech_chat_domain", "--issue-challenge", str(challenge), stdout=output)
            issue.assert_called_once_with()
            inspect.assert_not_called()
            apply.assert_not_called()
            self.assertEqual(challenge.stat().st_mode & 0o777, 0o600)
            call_command("verify_arnatech_chat_domain", "--challenge-file", str(challenge), stdout=output)
            inspect.assert_called_once_with("synthetic-manifest")
            apply.assert_not_called()
            self.assertFalse(receipt.exists())
            call_command("verify_arnatech_chat_domain", "--challenge-file", str(challenge), "--write-receipt", str(receipt),
                         stdout=output)
            self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
            link = Path(tmp) / "link"
            link.symlink_to(receipt)
            for bad_path in (link, Path(tmp) / "missing"):
                with self.assertRaises(CommandError):
                    call_command("verify_arnatech_chat_domain", "--challenge-file", str(challenge),
                                 "--apply-receipt", str(bad_path), stdout=output)
            receipt.chmod(0o644)
            with self.assertRaises(CommandError):
                call_command("verify_arnatech_chat_domain", "--challenge-file", str(challenge),
                             "--apply-receipt", str(receipt), stdout=output)
            apply.assert_not_called()
            receipt.chmod(0o600)
            call_command("verify_arnatech_chat_domain", "--challenge-file", str(challenge),
                         "--apply-receipt", str(receipt), stdout=output)
            apply.assert_called_once_with("synthetic-receipt", "synthetic-manifest")
            with self.assertRaises(CommandError):
                call_command("verify_arnatech_chat_domain", "--host", "other.example.test", stdout=output)
        self.assertIn("Dry run", output.getvalue())
        self.assertNotIn("synthetic-", output.getvalue())
