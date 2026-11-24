"""Pure synthetic policy tests. No Django, sockets, provider credentials or DB."""
import copy
import unittest
from core.domain_proof_policy import (
    ProofError, TTL, binding_for, digest, issue_receipt, read_receipt,
    require_same_state, verified_evidence,
)

KEY = "synthetic-unit-test-only-key-1234567890"
SNAPSHOT = {"domain_id": 174, "host": "example.test",
            "tenant_id": "10996862-26be-4c7a-8a05-acb814f77975",
            "organization_id": "25c1bf82-5eac-4507-a5d7-b1e271fdbb9f",
            "actor_id": "ae08e7ab-62b2-4425-89b2-830d710a7c97",
            "challenge_hash": digest("synthetic-challenge"), "method": "txt"}
BINDING = {"host": "example.test", "organization_id": SNAPSHOT["organization_id"],
           "project_id": "prj_synthetic", "team_id": "team_synthetic"}
PROJECT = {"id": BINDING["project_id"], "accountId": BINDING["team_id"]}
DOMAIN = {"name": BINDING["host"], "projectId": BINDING["project_id"], "verified": True}


class PolicyTests(unittest.TestCase):
    def evidence(self):
        return verified_evidence(PROJECT, DOMAIN, BINDING)

    def receipt(self):
        return issue_receipt(SNAPSHOT, BINDING, self.evidence(), KEY, now=1000)

    def test_valid_server_binding(self):
        self.assertEqual(binding_for(SNAPSHOT, {SNAPSHOT["tenant_id"]: BINDING}), BINDING)

    def test_no_tenant_or_host_fallback(self):
        for bindings in ({}, None, {SNAPSHOT["tenant_id"]: {**BINDING, "host": "other.test"}},
                         {SNAPSHOT["tenant_id"]: {**BINDING, "organization_id": "other"}}):
            with self.subTest(bindings=bindings), self.assertRaises(ProofError):
                binding_for(SNAPSHOT, bindings)

    def test_invalid_provider_ids_rejected(self):
        for key in ("project_id", "team_id"):
            for value in ("", "../secret", "https://internal", "name"):
                binding = {**BINDING, key: value}
                with self.subTest(key=key, value=value), self.assertRaises(ProofError):
                    binding_for(SNAPSHOT, {SNAPSHOT["tenant_id"]: binding})

    def test_bad_hosts_and_numeric_identity_rejected(self):
        for key, value in (("host", "https://example.test"), ("host", "127.0.0.1"), ("host", "Example.test"),
                           ("host", "example.test:443"), ("tenant_id", 85), ("domain_id", True), ("actor_id", "")):
            with self.subTest(key=key, value=value), self.assertRaises(ProofError):
                binding_for({**SNAPSHOT, key: value}, {})

    def test_provider_must_match_exact_team_project_and_host(self):
        for project, domain in (({**PROJECT, "accountId": "team_other"}, DOMAIN),
                                ({**PROJECT, "id": "prj_other"}, DOMAIN),
                                (PROJECT, {**DOMAIN, "name": "other.test"}),
                                (PROJECT, {**DOMAIN, "projectId": "prj_other"})):
            with self.subTest(project=project, domain=domain), self.assertRaises(ProofError):
                verified_evidence(project, domain, BINDING)

    def test_truthy_strings_do_not_count_as_verified(self):
        for value in (False, "true", 1, None):
            with self.subTest(value=value), self.assertRaises(ProofError):
                verified_evidence(PROJECT, {**DOMAIN, "verified": value}, BINDING)

    def test_preview_custom_environment_and_redirect_rejected(self):
        for key in ("gitBranch", "customEnvironmentId", "redirect"):
            with self.subTest(key=key), self.assertRaises(ProofError):
                verified_evidence(PROJECT, {**DOMAIN, key: "not-production"}, BINDING)

    def test_evidence_excludes_provider_response_secrets(self):
        evidence = verified_evidence({**PROJECT, "secret": "not-retained"}, DOMAIN, BINDING)
        self.assertNotIn("secret", str(evidence))

    def test_receipt_roundtrip(self):
        claims = read_receipt(self.receipt(), KEY, now=1001)
        require_same_state(claims, SNAPSHOT, BINDING, self.evidence())

    def test_tampered_receipt_and_wrong_key_rejected(self):
        receipt = self.receipt()
        for value, key in ((receipt[:-1] + ("0" if receipt[-1] != "0" else "1"), KEY),
                           (receipt, KEY + "other"), ("invalid", KEY), ("x" * 4097, KEY)):
            with self.subTest(value=value[:12]), self.assertRaises(ProofError):
                read_receipt(value, key, now=1001)

    def test_exact_expiry_and_future_issue_time_rejected(self):
        for now in (999, 1000 + TTL, 999999):
            with self.subTest(now=now), self.assertRaises(ProofError):
                read_receipt(self.receipt(), KEY, now=now)

    def test_missing_or_weak_signer_fails_closed(self):
        for key in ("", None, "short"):
            with self.subTest(key=key), self.assertRaises(ProofError):
                issue_receipt(SNAPSHOT, BINDING, self.evidence(), key, now=1000)

    def test_each_snapshot_field_change_invalidates_receipt(self):
        claims = read_receipt(self.receipt(), KEY, now=1001)
        for key, value in (("domain_id", 175), ("host", "other.test"), ("method", "vercel-api-v1"),
                           ("tenant_id", "20996862-26be-4c7a-8a05-acb814f77975"),
                           ("organization_id", "35c1bf82-5eac-4507-a5d7-b1e271fdbb9f"),
                           ("actor_id", "be08e7ab-62b2-4425-89b2-830d710a7c97"),
                           ("challenge_hash", digest("rotated"))):
            with self.subTest(key=key), self.assertRaises(ProofError):
                require_same_state(claims, {**SNAPSHOT, key: value}, BINDING, self.evidence())

    def test_configuration_change_invalidates_receipt(self):
        claims = read_receipt(self.receipt(), KEY, now=1001)
        with self.assertRaises(ProofError):
            require_same_state(claims, SNAPSHOT, {**BINDING, "team_id": "team_new"}, self.evidence())

    def test_provider_evidence_change_invalidates_receipt(self):
        claims = read_receipt(self.receipt(), KEY, now=1001)
        with self.assertRaises(ProofError):
            require_same_state(claims, SNAPSHOT, BINDING, {**self.evidence(), "host": "other.test"})


if __name__ == "__main__":
    unittest.main()

class RuntimeProofConfigTests(unittest.TestCase):
    def setUp(self):
        import json
        from config.domain_proof_config import read_vercel_proof_config
        from core.domain_proof_scope import PILOT_HOST, PILOT_ORGANIZATION, PILOT_TENANT
        self.read = read_vercel_proof_config
        self.bindings = {PILOT_TENANT: {**BINDING, 'host': PILOT_HOST, 'organization_id': PILOT_ORGANIZATION}}
        self.env = {
            "DOMAIN_VERCEL_PROOF_ENABLED": "true",
            "DOMAIN_VERCEL_RECEIPT_KEY": KEY,
            "DOMAIN_VERCEL_API_TOKEN": "synthetic-credential",
            "DOMAIN_VERCEL_PROOF_BINDINGS": json.dumps(self.bindings),
            "DOMAIN_VERCEL_PROOF_OPERATOR_ID": SNAPSHOT["actor_id"],
        }

    def test_explicit_opt_in_only(self):
        for flag in ("", "false", "TRUE", "1"):
            self.assertEqual(self.read({**self.env, "DOMAIN_VERCEL_PROOF_ENABLED": flag}, KEY),
                             (False, "", "", {}, ""))
        self.assertEqual(self.read(self.env, "different-django-key"),
                         (True, KEY, "synthetic-credential", self.bindings, SNAPSHOT["actor_id"]))

    def test_incomplete_ambiguous_or_reused_credentials_rejected_without_value_echo(self):
        for changes, django_key in (
            ({"DOMAIN_VERCEL_RECEIPT_KEY": "not-dedicated"}, "different"),
            ({}, KEY),
            ({"DOMAIN_VERCEL_PROOF_OPERATOR_ID": ""}, "different"),
            ({"DOMAIN_VERCEL_API_TOKEN": KEY}, "different"),
            ({"DOMAIN_VERCEL_API_TOKEN": "should-not-log-this\n"}, "different"),
            ({"DOMAIN_VERCEL_PROOF_BINDINGS": '{"same":{},"same":{}}'}, "different"),
            ({"DOMAIN_VERCEL_PROOF_BINDINGS": "🚫 secret data"}, "different"),
        ):
            with self.subTest(keys=tuple(changes)):
                with self.assertRaises(RuntimeError) as error:
                    self.read({**self.env, **changes}, django_key)
                self.assertEqual(str(error.exception),
                                 "Vercel ownership proof configuration rejected; inspect managed settings privately.")
