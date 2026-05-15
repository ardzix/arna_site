import tempfile
import os

from django.test import TestCase, override_settings, Client
from unittest.mock import patch
import uuid

from core.models import Tenant, Domain, Template, TemplateSection, TemplateBlock
from authentication.test_helpers import generate_rsa_keypair, make_jwt
from authentication.jwt_backends import ArnaJWTAuthentication
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


@override_settings(ALLOWED_HOSTS=['*'])
class E2EApplyTemplateTest(TestCase):
    def setUp(self):
        from django.db import connection
        connection.set_schema_to_public()

        self.public_tenant, _ = Tenant.objects.get_or_create(
            schema_name='public',
            defaults={'name': 'ArnaSite Global', 'slug': 'public', 'sso_organization_id': uuid.uuid4()}
        )
        Domain.objects.get_or_create(domain='testserver', tenant=self.public_tenant, is_primary=True)

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
        self.domain = 'tenant.localhost'
        Domain.objects.create(domain=self.domain, tenant=self.test_tenant, is_primary=True)
        self.private_pem, self.public_pem = generate_rsa_keypair()
        self.patcher = patch.object(
            ArnaJWTAuthentication,
            '_public_key_override',
            new=self.public_pem.decode(),
            create=True,
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def _auth(self):
        token = make_jwt(self.private_pem, uuid.uuid4(), self.tenant_org_id, roles=["site_admin"])
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_end_to_end_clone_workflow(self):
        """
        Full E2E: authenticated POST clones master template into tenant schema.
        Uses TenantClient to bypass domain-resolution and set schema directly.
        """
        client = Client(HTTP_HOST=self.domain)
        response = client.post(
            "/api/tenant/apply-template/",
            {"template_id": str(self.template.id)},
            **self._auth(),
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

    def test_apply_template_missing_template_id(self):
        """POST without template_id should return 400."""
        client = Client(HTTP_HOST=self.domain)
        response = client.post(
            "/api/tenant/apply-template/",
            {},
            **self._auth(),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("template_id", response.json()["error"])

    def test_apply_template_nonexistent_template_id(self):
        """POST with a random (non-existent) UUID should return 404."""
        client = Client(HTTP_HOST=self.domain)
        response = client.post(
            "/api/tenant/apply-template/",
            {"template_id": str(uuid.uuid4())},
            **self._auth(),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_apply_template_unauthenticated(self):
        """POST without auth header should return 401."""
        client = Client(HTTP_HOST=self.domain)
        response = client.post(
            "/api/tenant/apply-template/",
            {"template_id": str(self.template.id)},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_apply_template_overwrite_false_returns_409(self):
        """Applying with overwrite=False on domain with existing data should return 409."""
        # Populate existing data
        from django.db import connection
        connection.set_tenant(self.test_tenant)
        Section.objects.create(type="header", order=1)
        
        client = Client(HTTP_HOST=self.domain)
        payload = {"template_id": str(self.template.id), "overwrite": False}
        headers = self._auth()

        response = client.post("/api/tenant/apply-template/",
                               payload, content_type="application/json", **headers)

        self.assertEqual(response.status_code, 409)

    def test_apply_template_overwrite_true_replaces_content(self):
        """Applying with overwrite=True should succeed and wipe existing data."""
        # Populate existing data
        from django.db import connection
        connection.set_tenant(self.test_tenant)
        Section.objects.create(type="header", order=1)
        
        client = Client(HTTP_HOST=self.domain)
        payload = {"template_id": str(self.template.id), "overwrite": True}
        headers = self._auth()

        response = client.post("/api/tenant/apply-template/",
                               payload, content_type="application/json", **headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Section.objects.filter(type="hero").count(), 1,
            "Re-applying a template with overwrite=true must replace content"
        )


@override_settings(ALLOWED_HOSTS=['*'], ROOT_URLCONF='config.public_urls')
class PublicTemplateVisibilityTest(TestCase):
    def setUp(self):
        from django.db import connection
        connection.set_schema_to_public()

        self.public_tenant, _ = Tenant.objects.get_or_create(
            schema_name='public',
            defaults={
                'name': 'ArnaSite Global',
                'slug': 'public',
                'sso_organization_id': uuid.uuid4(),
            }
        )
        Domain.objects.get_or_create(domain='testserver', tenant=self.public_tenant, is_primary=True)

        self.public_template = Template.objects.create(
            name='Published Template',
            slug='published-template',
            is_published=True,
        )
        self.private_template = Template.objects.create(
            name='Private Template',
            slug='private-template',
            is_published=False,
            source_tenant_schema='tenant_alpha',
        )

    def test_public_catalog_hides_private_templates(self):
        response = self.client.get("/templates/")
        self.assertEqual(response.status_code, 200)
        slugs = {item["slug"] for item in response.json()}
        self.assertIn(self.public_template.slug, slugs)
        self.assertNotIn(self.private_template.slug, slugs)

    def test_public_template_detail_rejects_private_template(self):
        response = self.client.get(f"/templates/{self.private_template.id}/")
        self.assertEqual(response.status_code, 404)


@override_settings(ALLOWED_HOSTS=['*'], ROOT_URLCONF='config.public_urls')
class TenantRegistrationAudienceTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_pem, cls.public_pem = generate_rsa_keypair()
        cls.key_file = tempfile.NamedTemporaryFile(suffix='.pem', delete=False)
        cls.key_file.write(cls.public_pem)
        cls.key_file.close()

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.key_file.name)
        super().tearDownClass()

    def setUp(self):
        from django.db import connection
        connection.set_schema_to_public()
        public_tenant, _ = Tenant.objects.get_or_create(
            schema_name='public',
            defaults={'name': 'ArnaSite Global', 'slug': 'public', 'sso_organization_id': uuid.uuid4()},
        )
        Domain.objects.get_or_create(domain='testserver', tenant=public_tenant, is_primary=True)

    def test_register_rejects_wrong_audience_token(self):
        token = make_jwt(
            self.private_pem,
            uuid.uuid4(),
            uuid.uuid4(),
            is_owner=True,
            aud="some_other_service",
        )
        with override_settings(SSO_JWT_PUBLIC_KEY_PATH=self.key_file.name, SSO_JWT_AUDIENCE='arnasite'):
            response = self.client.post(
                "/tenants/register/",
                {"name": "Tenant Baru", "slug": "tenant-baru", "domain": "tenant-baru.localhost"},
                HTTP_AUTHORIZATION=f"Bearer {token}",
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 401)
