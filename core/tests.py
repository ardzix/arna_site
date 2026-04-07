from django.test import TestCase
from django_tenants.test.client import TenantClient
from unittest.mock import patch
import uuid

from core.models import Tenant, Domain, Template, TemplateSection, TemplateBlock
from sites.models import Section, ContentBlock


def _make_auth_mock(org_id_str):
    """Helper: returns a side_effect fn that mocks both SSO endpoints."""
    class MockMe:
        def json(self): return {"id": str(uuid.uuid4()), "email": "user@arna.com"}
        def raise_for_status(self): pass

    class MockOrg:
        def json(self): return {"id": org_id_str}
        def raise_for_status(self): pass

    def side_effect(url, *args, **kwargs):
        if "auth/me" in url:
            return MockMe()
        elif "organizations/current" in url:
            return MockOrg()
        raise Exception(f"Unmocked SSO URL: {url}")

    return side_effect


class E2EApplyTemplateTest(TestCase):
    def setUp(self):
        from django.db import connection
        connection.set_schema_to_public()

        self.public_tenant = Tenant.objects.create(
            schema_name='public', name='ArnaSite Global',
            slug='public', sso_organization_id=uuid.uuid4()
        )
        Domain.objects.create(domain='localhost', tenant=self.public_tenant, is_primary=True)

        # Master Template Blueprint (in public schema)
        self.template = Template.objects.create(name='Test Master', slug='test-master')
        self.t_section = TemplateSection.objects.create(
            template=self.template, type='hero', order=1
        )
        self.t_block = TemplateBlock.objects.create(
            section=self.t_section, title='Hero Block', order=1
        )

        self.tenant_org_id = uuid.uuid4()
        self.test_tenant = Tenant.objects.create(
            schema_name='tenant_mock_01', name='Company XYZ',
            slug='company-xyz', sso_organization_id=self.tenant_org_id
        )
        Domain.objects.create(domain='tenant.localhost', tenant=self.test_tenant, is_primary=True)

    @patch('authentication.backends.http.get')
    def test_end_to_end_clone_workflow(self, mock_get):
        """
        Full E2E: authenticated POST clones master template into tenant schema.
        Uses TenantClient to bypass domain-resolution and set schema directly.
        """
        mock_get.side_effect = _make_auth_mock(str(self.tenant_org_id))

        client = TenantClient(self.test_tenant)
        response = client.post(
            "/api/tenants/current/apply-template/",
            {"template_id": str(self.template.id)},
            HTTP_AUTHORIZATION="Bearer fake_jwt_token",
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code, 200,
            f"API Failed [{response.status_code}]: {response.content}"
        )

        # Verify data was cloned into the tenant schema
        from django.db import connection
        connection.set_tenant(self.test_tenant)
        self.assertTrue(
            Section.objects.filter(type="hero").exists(),
            "Section was not cloned into tenant schema"
        )
        self.assertTrue(
            ContentBlock.objects.filter(title="Hero Block").exists(),
            "ContentBlock was not cloned into tenant schema"
        )

    @patch('authentication.backends.http.get')
    def test_apply_template_missing_template_id(self, mock_get):
        """POST without template_id should return 400."""
        mock_get.side_effect = _make_auth_mock(str(self.tenant_org_id))

        client = TenantClient(self.test_tenant)
        response = client.post(
            "/api/tenants/current/apply-template/",
            {},
            HTTP_AUTHORIZATION="Bearer fake_jwt_token",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("template_id", response.json()["error"])

    @patch('authentication.backends.http.get')
    def test_apply_template_nonexistent_template_id(self, mock_get):
        """POST with a random (non-existent) UUID should return 404."""
        mock_get.side_effect = _make_auth_mock(str(self.tenant_org_id))

        client = TenantClient(self.test_tenant)
        response = client.post(
            "/api/tenants/current/apply-template/",
            {"template_id": str(uuid.uuid4())},
            HTTP_AUTHORIZATION="Bearer fake_jwt_token",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_apply_template_unauthenticated(self):
        """POST without auth header should return 401."""
        client = TenantClient(self.test_tenant)
        response = client.post(
            "/api/tenants/current/apply-template/",
            {"template_id": str(self.template.id)},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    @patch('authentication.backends.http.get')
    def test_apply_template_idempotent(self, mock_get):
        """Applying the same template twice must not create duplicate sections."""
        mock_get.side_effect = _make_auth_mock(str(self.tenant_org_id))

        client = TenantClient(self.test_tenant)
        payload = {"template_id": str(self.template.id)}
        headers = {"HTTP_AUTHORIZATION": "Bearer fake_jwt_token"}

        client.post("/api/tenants/current/apply-template/",
                    payload, content_type="application/json", **headers)
        client.post("/api/tenants/current/apply-template/",
                    payload, content_type="application/json", **headers)

        from django.db import connection
        connection.set_tenant(self.test_tenant)
        self.assertEqual(
            Section.objects.filter(type="hero").count(), 1,
            "Re-applying a template must replace content, not duplicate it"
        )
