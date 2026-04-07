from django.test import TestCase, Client
from unittest.mock import patch
import uuid

from core.models import Tenant, Domain, Template, TemplateSection, TemplateBlock
from sites.models import Section, ContentBlock

class E2EApplyTemplateTest(TestCase):
    def setUp(self):
        from django.db import connection
        connection.set_schema_to_public()
        
        # 1. Create Public Tenant
        self.public_tenant = Tenant.objects.create(
            schema_name='public',
            name='ArnaSite Global',
            slug='public',
            sso_organization_id=uuid.uuid4()
        )
        Domain.objects.create(domain='localhost', tenant=self.public_tenant, is_primary=True)

        # 2. Create Master Template Blueprint in public schema
        self.template = Template.objects.create(name='Test Master', slug='test-master')
        self.t_section = TemplateSection.objects.create(template=self.template, type='hero', order=1)
        self.t_block = TemplateBlock.objects.create(section=self.t_section, title='Hero Block', order=1)

        # 3. Create Tenant
        self.tenant_org_id = uuid.uuid4()
        self.test_tenant = Tenant.objects.create(
            schema_name='tenant_mock_01',
            name='Company XYZ',
            slug='company-xyz',
            sso_organization_id=self.tenant_org_id
        )
        Domain.objects.create(domain='tenant.localhost', tenant=self.test_tenant, is_primary=True)

    @patch('authentication.backends.http.get')
    def test_end_to_end_clone_workflow(self, mock_get):
        """
        Simulates an API request from 'tenant.localhost' and mocks the 
        Arna SSO backend token validation to prove End-to-End correctness.
        """
        # Create response mock for /auth/me/
        class MockMeResponse:
            status_code = 200
            def json(self): return {"id": str(uuid.uuid4()), "email": "user@arna.com"}
            def raise_for_status(self): pass

        tenant_org_id_str = str(self.tenant_org_id)
        class MockOrgResponse:
            status_code = 200
            def json(self): return {"id": tenant_org_id_str}
            def raise_for_status(self): pass

        def side_effect(url, *args, **kwargs):
            if "auth/me" in url:
                return MockMeResponse()
            elif "organizations/current" in url:
                return MockOrgResponse()
            raise Exception(f"Unmocked URL: {url}")

        mock_get.side_effect = side_effect

        # 4. Make an Authenticated POST to the cloned API endpoint
        # The HTTP_HOST tells TenantMainMiddleware to lock onto `tenant_mock_01`
        client = Client(HTTP_HOST='tenant.localhost')
        response = client.post(
            "/api/tenants/current/apply-template/",
            {"template_id": str(self.template.id)},
            HTTP_AUTHORIZATION="Bearer fake_jwt_token",
            content_type="application/json"
        )

        # 5. Assert the API succeeded
        self.assertEqual(response.status_code, 200, f"API Failed: {response.json() if hasattr(response, 'json') else response.content}")
        
        # 6. Verify isolation! Read from the tenant's exact schema
        from django.db import connection
        connection.set_tenant(self.test_tenant)
        
        self.assertTrue(Section.objects.filter(type="hero").exists(), "Section failed to clone into tenant schema")
        self.assertTrue(ContentBlock.objects.filter(title="Hero Block").exists(), "Block failed to clone into tenant schema")
