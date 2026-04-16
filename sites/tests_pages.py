import os
import tempfile
import uuid

from django.test import TestCase, override_settings
from django.db import connection
from django_tenants.test.client import TenantClient
from unittest.mock import patch

from authentication.test_helpers import generate_rsa_keypair, make_jwt
from authentication.jwt_backends import ArnaJWTAuthentication
from core.models import Domain, Tenant
from sites.models import Page, Section


@override_settings(ALLOWED_HOSTS=['*'])
class PageSectionReorderScopeTest(TestCase):
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
        connection.set_schema_to_public()
        self.org_id = uuid.uuid4()
        self.tenant = Tenant.objects.create(
            schema_name='tenant_page_reorder',
            name='Page Reorder',
            slug='page-reorder',
            sso_organization_id=self.org_id,
        )
        Domain.objects.create(domain='page-reorder.localhost', tenant=self.tenant, is_primary=True)

        self.settings_override = override_settings(
            SSO_JWT_PUBLIC_KEY_PATH=self.key_file.name,
            SSO_JWT_AUDIENCE='arnasite',
        )
        self.settings_override.enable()
        self.patcher = patch.object(
            ArnaJWTAuthentication,
            '_public_key_override',
            new=self.public_pem.decode(),
            create=True,
        )
        self.patcher.start()

        self.client = TenantClient(self.tenant)
        self.auth = {
            "HTTP_AUTHORIZATION": f"Bearer {make_jwt(self.private_pem, uuid.uuid4(), self.org_id, roles=['site_admin'])}"
        }

        connection.set_tenant(self.tenant)
        self.page_a = Page.objects.create(title="Home", slug="home", order=1)
        self.page_b = Page.objects.create(title="About", slug="about", order=2)
        self.section_a = Section.objects.create(page=self.page_a, type="hero", order=1)
        self.section_b = Section.objects.create(page=self.page_b, type="about", order=9)
        connection.set_schema_to_public()

    def tearDown(self):
        self.patcher.stop()
        self.settings_override.disable()

    def test_reorder_only_updates_sections_within_requested_page(self):
        response = self.client.patch(
            f"/api/pages/{self.page_a.id}/sections/reorder/",
            [
                {"id": str(self.section_a.id), "order": 5},
                {"id": str(self.section_b.id), "order": 1},
            ],
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)

        connection.set_tenant(self.tenant)
        self.section_a.refresh_from_db()
        self.section_b.refresh_from_db()
        self.assertEqual(self.section_a.order, 5)
        self.assertEqual(self.section_b.order, 9)
