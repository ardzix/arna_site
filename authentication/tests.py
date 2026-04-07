from django.test import TestCase, Client
from unittest.mock import patch
import uuid
from core.models import Tenant, Domain

class AuthenticationTest(TestCase):
    def setUp(self):
        from django.db import connection
        connection.set_schema_to_public()
        
        self.org_id = uuid.uuid4()
        self.tenant = Tenant.objects.create(
            schema_name='tenant_auth_test',
            name='Auth Test',
            slug='auth-test',
            sso_organization_id=self.org_id
        )
        Domain.objects.create(domain='auth.localhost', tenant=self.tenant, is_primary=True)
        
        self.other_tenant = Tenant.objects.create(
            schema_name='tenant_auth_other',
            name='Auth Other',
            slug='auth-other',
            sso_organization_id=uuid.uuid4()
        )
        Domain.objects.create(domain='other.localhost', tenant=self.other_tenant, is_primary=True)

    @patch('authentication.backends.http.get')
    def test_invalid_token_rejected(self, mock_get):
        import requests as http
        class MockFailedResponse:
            status_code = 401
            def raise_for_status(self): raise http.RequestException("401")
            
        mock_get.return_value = MockFailedResponse()

        client = Client(HTTP_HOST='auth.localhost')
        response = client.get("/api/sites/sections/", HTTP_AUTHORIZATION="Bearer badtoken")
        
        self.assertEqual(response.status_code, 401)

    @patch('authentication.backends.http.get')
    def test_cross_tenant_access_forbidden(self, mock_get):
        # User is authenticated but belongs to self.tenant (tenant_auth_test)
        org_id_str = str(self.org_id)
        class MockMeResponse:
            def json(self): return {"id": str(uuid.uuid4()), "email": "admin@arna.com"}
            def raise_for_status(self): pass
        class MockOrgResponse:
            def json(self): return {"id": org_id_str}
            def raise_for_status(self): pass

        def side_effect(url, *args, **kwargs):
            if "auth/me" in url: return MockMeResponse()
            elif "organizations/current" in url: return MockOrgResponse()

        mock_get.side_effect = side_effect

        # User attempts to access OTHER tenant's subdomain
        client = Client(HTTP_HOST='other.localhost')
        response = client.get("/api/sites/sections/", HTTP_AUTHORIZATION="Bearer ok_token")
        
        # Should be rejected because IsTenantMember realizes the request's connection.tenant 
        # is 'tenant_auth_other' but user's cached tenant_schema is 'tenant_auth_test'
        self.assertEqual(response.status_code, 403)
