"""Isolated HTTPS signing, nonce purpose, and immutable config tests."""
import unittest
from unittest.mock import patch

from config.domain_proof_config import read_https_proof_config
from core.domain_proof_policy import (CHALLENGE_SALT, CHALLENGE_TTL, ProofError, digest,
    issue_receipt, read_receipt, require_same_state, validate_snapshot)
from core.domain_proof_operator import read_challenge

KEY = "synthetic-unit-test-only-key-1234567890"
SNAPSHOT = {"domain_id": 174, "host": "arnatech.id",
            "tenant_id": "10996862-26be-4c7a-8a05-acb814f77975",
            "organization_id": "25c1bf82-5eac-4507-a5d7-b1e271fdbb9f",
            "actor_id": "ae08e7ab-62b2-4425-89b2-830d710a7c97",
            "challenge_hash": digest("synthetic-challenge"), "method": "txt"}
EVIDENCE = {"provider": "https-origin-v1", "tls_verified": True}
BINDING = {"manifest_hash": "a" * 64}


class PolicyTests(unittest.TestCase):
    def receipt(self):
        return issue_receipt(SNAPSHOT, BINDING, EVIDENCE, KEY, now=1000)

    def test_snapshot_does_not_admit_numeric_identity_or_urls(self):
        for change in ({"tenant_id": 85}, {"host": "https://arnatech.id"}, {"domain_id": "174"}):
            with self.subTest(change=change), self.assertRaises(ProofError):
                validate_snapshot({**SNAPSHOT, **change})

    def test_exact_expiry_and_future_issue_time_reject(self):
        self.assertEqual(read_receipt(self.receipt(), KEY, now=1119)["snapshot"], SNAPSHOT)
        for now in (999, 1120):
            with self.assertRaises(ProofError):
                read_receipt(self.receipt(), KEY, now=now)

    def test_tampering_wrong_key_and_state_changes_reject(self):
        token = self.receipt()
        claims = read_receipt(token, KEY, now=1000)
        for altered, key in ((token, KEY + "wrong"), (token[:-1] + ("1" if token[-1] != "1" else "0"), KEY)):
            with self.assertRaises(ProofError):
                read_receipt(altered, key, now=1000)
        for k in SNAPSHOT:
            with self.subTest(key=k), self.assertRaises(ProofError):
                require_same_state(claims, {**SNAPSHOT, k: "wrong"}, BINDING, EVIDENCE)
        with self.assertRaises(ProofError):
            require_same_state(claims, SNAPSHOT, BINDING, {"provider": "other"})

    def test_signed_challenge_has_independent_purpose_exact_scope_and_lifetime(self):
        value = "arnatech-bnk-https-v1 " + "a" * 64 + " 1795540900"
        manifest = issue_receipt(SNAPSHOT, {"publish_value": value}, {"kind": "fixture"}, KEY,
                                 now=1795540000, ttl=CHALLENGE_TTL, salt=CHALLENGE_SALT)
        with self.assertRaises(ProofError):
            read_receipt(manifest, KEY, now=1795540001)
        with patch("core.domain_proof_policy.time.time", return_value=1795540001):
            self.assertEqual(read_challenge(manifest, KEY, SNAPSHOT), value)
            with self.assertRaises(ProofError):
                read_challenge(manifest, KEY, {**SNAPSHOT, "domain_id": 999})
        with patch("core.domain_proof_policy.time.time", return_value=1795540900), self.assertRaises(ProofError):
            read_challenge(manifest, KEY, SNAPSHOT)

    def test_config_needs_independent_signer_and_exact_opt_in_no_provider_token(self):
        env = {"DOMAIN_HTTPS_PROOF_ENABLED": "true", "DOMAIN_HTTPS_PROOF_OPERATOR_ID": SNAPSHOT["actor_id"],
               "DOMAIN_HTTPS_RECEIPT_KEY": KEY}
        for flag in ("", "false", "TRUE", "1"):
            self.assertEqual(read_https_proof_config({**env, "DOMAIN_HTTPS_PROOF_ENABLED": flag}, KEY),
                             (False, "", ""))
        self.assertEqual(read_https_proof_config(env, "distinct-django-secret"),
                         (True, KEY, SNAPSHOT["actor_id"]))
        for data, secret in ((env, KEY), ({**env, "DOMAIN_HTTPS_PROOF_OPERATOR_ID": "bogus"}, "other"),
                             ({**env, "DOMAIN_HTTPS_RECEIPT_KEY": "short"}, "other")):
            with self.assertRaisesRegex(RuntimeError, "configuration rejected"):
                read_https_proof_config(data, secret)
