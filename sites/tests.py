from django.test import TestCase, Client
from unittest.mock import patch
import uuid
from core.models import Tenant, Domain

class SitesCRUDTest(TestCase):
    def setUp(self):
        from django.db import connection
        connection.set_schema_to_public()
        
        self.org_id = uuid.uuid4()
        self.tenant = Tenant.objects.create(
            schema_name='tenant_sites_test',
            name='Sites Test',
            slug='sites-test',
            sso_organization_id=self.org_id
        )
        Domain.objects.create(domain='sites.localhost', tenant=self.tenant, is_primary=True)

    @patch('authentication.backends.http.get')
    def test_tenant_crud_operations(self, mock_get):
        org_id_str = str(self.org_id)
        class MockMeResponse:
            def json(self): return {"id": str(uuid.uuid4()), "email": "owner@arna.com"}
            def raise_for_status(self): pass
        class MockOrgResponse:
            def json(self): return {"id": org_id_str}
            def raise_for_status(self): pass
            
        def side_effect(url, *args, **kwargs):
            if "auth/me" in url: return MockMeResponse()
            elif "organizations/current" in url: return MockOrgResponse()

        mock_get.side_effect = side_effect

        client = Client(HTTP_HOST='sites.localhost')
        
        # POST - Create Section
        resp_post = client.post(
            "/api/sites/sections/", 
            {"type": "hero", "order": 1, "is_active": True},
            HTTP_AUTHORIZATION="Bearer valid_token",
            content_type="application/json"
        )
        self.assertEqual(resp_post.status_code, 201)
        
        # GET - List Sections
        resp_get = client.get("/api/sites/sections/", HTTP_AUTHORIZATION="Bearer valid_token")
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(len(resp_get.json()), 1)
        
        # Verify isolation via direct DB check
        from django.db import connection
        connection.set_tenant(self.tenant)
        from sites.models import Section
        self.assertEqual(Section.objects.count(), 1)
