from django.test import TestCase
from django_tenants.test.client import TenantClient
from unittest.mock import patch
import uuid
from core.models import Tenant, Domain


def _make_auth_mock(org_id_str):
    class MockMe:
        def json(self): return {"id": str(uuid.uuid4()), "email": "admin@arna.com"}
        def raise_for_status(self): pass

    class MockOrg:
        def json(self): return {"id": org_id_str}
        def raise_for_status(self): pass

    def side_effect(url, *args, **kwargs):
        if "auth/me" in url: return MockMe()
        elif "organizations/current" in url: return MockOrg()
        raise Exception(f"Unmocked URL: {url}")

    return side_effect


class AuthenticationTest(TestCase):
    def setUp(self):
        from django.db import connection
        connection.set_schema_to_public()

        self.org_id = uuid.uuid4()
        self.tenant = Tenant.objects.create(
            schema_name='tenant_auth_test', name='Auth Test',
            slug='auth-test', sso_organization_id=self.org_id
        )
        Domain.objects.create(domain='auth.localhost', tenant=self.tenant, is_primary=True)

        self.other_org_id = uuid.uuid4()
        self.other_tenant = Tenant.objects.create(
            schema_name='tenant_auth_other', name='Auth Other',
            slug='auth-other', sso_organization_id=self.other_org_id
        )
        Domain.objects.create(domain='other.localhost', tenant=self.other_tenant, is_primary=True)

    @patch('authentication.backends.http.get')
    def test_invalid_token_rejected(self, mock_get):
        """A token that fails SSO validation must return 401."""
        import requests
        class MockFailed:
            status_code = 401
            def raise_for_status(self): raise requests.RequestException("401 Unauthorized")

        mock_get.return_value = MockFailed()

        client = TenantClient(self.tenant)
        response = client.get("/api/sites/sections/",
                              HTTP_AUTHORIZATION="Bearer badtoken")
        self.assertEqual(response.status_code, 401)

    @patch('authentication.backends.http.get')
    def test_cross_tenant_access_forbidden(self, mock_get):
        """
        User authenticated against self.tenant tries to access self.other_tenant
        endpoints. IsTenantMember must reject this with 403.
        """
        # SSO says user belongs to self.tenant (org_id)
        mock_get.side_effect = _make_auth_mock(str(self.org_id))

        # But TenantClient is set to other_tenant's schema
        client = TenantClient(self.other_tenant)
        response = client.get("/api/sites/sections/",
                              HTTP_AUTHORIZATION="Bearer ok_token")
        self.assertEqual(response.status_code, 403)

    def test_missing_auth_header_returns_401(self):
        """Requests with no Authorization header must return 401."""
        client = TenantClient(self.tenant)
        response = client.get("/api/sites/sections/")
        self.assertEqual(response.status_code, 401)

    @patch('authentication.backends.http.get')
    def test_valid_token_grants_access(self, mock_get):
        """A valid token belonging to the correct tenant must get 200."""
        mock_get.side_effect = _make_auth_mock(str(self.org_id))

        client = TenantClient(self.tenant)
        response = client.get("/api/sites/sections/",
                              HTTP_AUTHORIZATION="Bearer good_token")
        self.assertEqual(response.status_code, 200)
