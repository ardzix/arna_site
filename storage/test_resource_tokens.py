import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jwt
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from storage.resource_tokens import storage_headers, StorageExchangeUnavailable


@override_settings(ARNA_SSO_BASE_URL="https://sso.arnatech.id/api", SSO_JWT_PUBLIC_KEY_PATH="synthetic")
class StorageResourceTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.request = SimpleNamespace(auth="synthetic-subject", user=SimpleNamespace(id="user", org_id="org"),
            tenant=SimpleNamespace(public_id="tenant", sso_organization_id="org"))
        self.claims = dict(exp=int(time.time())+60, iat=int(time.time()), jti="synthetic",
            iss="https://sso.arnatech.id", aud="storage", user_id="user", org_id="org", tenant_id="tenant",
            token_type="access", principal_type="user")

    def exchange(self, **overrides):
        token = jwt.encode({**self.claims, **overrides}, self.key, algorithm="RS256")
        with patch("storage.resource_tokens.get_cached_public_key", return_value=self.key.public_key()), patch(
            "storage.resource_tokens.requests.post", return_value=Mock(status_code=200, json=lambda: {"access_token": token})) as post:
            result = storage_headers(self.request)
        return result, post

    def test_exchange_uses_subject_and_only_storage_audience(self):
        result, post = self.exchange()
        self.assertNotEqual(result["Authorization"], "Bearer synthetic-subject")
        self.assertEqual(post.call_args.kwargs["json"], {"audience": "storage"})
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Bearer synthetic-subject"})
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    def test_other_workspace_or_subject_is_rejected(self):
        for changed in ({"org_id": "foreign"}, {"tenant_id": "foreign"}, {"user_id": "foreign"}, {"principal_type": "device"}):
            with self.subTest(changed=changed), self.assertRaises(PermissionDenied):
                self.exchange(**changed)

    def test_wrong_resource_or_expired_token_is_rejected(self):
        for changed in ({"aud": "arna-commerce"}, {"exp": 1}, {"iss": "https://foreign.example"}):
            with self.subTest(changed=changed), self.assertRaises(StorageExchangeUnavailable):
                self.exchange(**changed)

    def test_missing_workspace_does_not_call_sso(self):
        self.request.tenant = None
        with patch("storage.resource_tokens.requests.post") as post, self.assertRaises(PermissionDenied):
            storage_headers(self.request)
        post.assert_not_called()

    def test_sso_errors_do_not_leak_response_or_allow_fallback(self):
        for code, error in ((401, AuthenticationFailed), (403, PermissionDenied), (429, StorageExchangeUnavailable), (500, StorageExchangeUnavailable)):
            with self.subTest(code=code), patch("storage.resource_tokens.requests.post", return_value=Mock(status_code=code)), self.assertRaises(error):
                storage_headers(self.request)

    def test_network_failure_is_retryable(self):
        with patch("storage.resource_tokens.requests.post", side_effect=requests.Timeout), self.assertRaises(StorageExchangeUnavailable):
            storage_headers(self.request)

    def test_untrusted_sso_url_is_rejected_before_forwarding_subject(self):
        with override_settings(ARNA_SSO_BASE_URL="https://foreign.example/api"), patch("storage.resource_tokens.requests.post") as post, self.assertRaises(StorageExchangeUnavailable):
            storage_headers(self.request)
        post.assert_not_called()
