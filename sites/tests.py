from django.test import TestCase, override_settings, Client
from unittest.mock import patch
import uuid
from core.models import Tenant, Domain
from authentication.test_helpers import generate_rsa_keypair, make_jwt
from authentication.jwt_backends import ArnaJWTAuthentication
from sites.models import Page


@override_settings(ALLOWED_HOSTS=['*'])
class SitesCRUDTest(TestCase):
    def setUp(self):
        from django.db import connection
        connection.set_schema_to_public()

        self.org_id = uuid.uuid4()
        self.tenant = Tenant.objects.create(
            schema_name='tenant_sites_test', name='Sites Test',
            slug='sites-test', sso_organization_id=self.org_id
        )
        self.domain = 'sites.localhost'
        Domain.objects.create(domain=self.domain, tenant=self.tenant, is_primary=True)
        self.private_pem, self.public_pem = generate_rsa_keypair()
        self.patcher = patch.object(
            ArnaJWTAuthentication,
            '_public_key_override',
            new=self.public_pem.decode(),
            create=True,
        )
        self.patcher.start()
        from django.db import connection
        connection.set_tenant(self.tenant)
        self.page = Page.objects.create(title="Home", slug="home", order=1, is_home=True)
        connection.set_schema_to_public()

    def tearDown(self):
        self.patcher.stop()

    def _auth(self):
        token = make_jwt(self.private_pem, uuid.uuid4(), self.org_id, roles=["site_admin"])
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_tenant_crud_operations(self):
        """Create, list, and verify tenant-scoped sections via the API."""
        client = Client(HTTP_HOST=self.domain)
        auth = self._auth()

        # POST - Create Section
        resp_post = client.post(
            f"/api/pages/{self.page.id}/sections/",
            {"type": "hero", "order": 1, "is_active": True},
            content_type="application/json", **auth
        )
        self.assertEqual(resp_post.status_code, 201,
                         f"Create failed: {resp_post.content}")

        section_id = resp_post.json()["id"]

        # GET - List Sections
        resp_get = client.get(f"/api/pages/{self.page.id}/sections/", **auth)
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(len(resp_get.json()), 1)

        # PATCH - Update Section
        resp_patch = client.patch(
            f"/api/pages/{self.page.id}/sections/{section_id}/",
            {"type": "about"},
            content_type="application/json", **auth
        )
        self.assertEqual(resp_patch.status_code, 200)
        self.assertEqual(resp_patch.json()["type"], "about")

        # DELETE - Remove Section
        resp_delete = client.delete(f"/api/pages/{self.page.id}/sections/{section_id}/", **auth)
        self.assertEqual(resp_delete.status_code, 204)

        # Confirm deletion
        resp_get2 = client.get(f"/api/pages/{self.page.id}/sections/", **auth)
        self.assertEqual(len(resp_get2.json()), 0)

    def test_filter_blocks_by_section(self):
        """GET /api/sites/blocks/?section=<id> only returns blocks for that section."""
        client = Client(HTTP_HOST=self.domain)
        auth = self._auth()

        # Create two sections
        s1 = client.post(f"/api/pages/{self.page.id}/sections/",
                         {"type": "hero", "order": 1},
                         content_type="application/json", **auth).json()
        s2 = client.post(f"/api/pages/{self.page.id}/sections/",
                         {"type": "about", "order": 2},
                         content_type="application/json", **auth).json()

        # Create a block under s1 only
        client.post(f"/api/pages/{self.page.id}/sections/{s1['id']}/blocks/",
                    {"order": 1},
                    content_type="application/json", **auth)

        # Filter by s1 — expect 1
        resp = client.get(f"/api/pages/{self.page.id}/sections/{s1['id']}/blocks/", **auth)
        self.assertEqual(len(resp.json()), 1)

        # Filter by s2 — expect 0
        resp2 = client.get(f"/api/pages/{self.page.id}/sections/{s2['id']}/blocks/", **auth)
        self.assertEqual(len(resp2.json()), 0)

    def test_public_site_view_no_auth_required(self):
        """GET /public/site/ must return 200 without any auth header."""
        client = Client(HTTP_HOST=self.domain)

        resp = client.get("/api/public/site/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("tenant", data)
        self.assertIn("pages", data)
        self.assertEqual(data["tenant"]["slug"], "sites-test")

    def test_schema_isolation(self):
        """Direct DB check: sections only exist in the correct tenant schema."""
        client = Client(HTTP_HOST=self.domain)
        auth = self._auth()

        client.post(f"/api/pages/{self.page.id}/sections/",
                    {"type": "hero", "order": 1},
                    content_type="application/json", **auth)

        from django.db import connection
        connection.set_tenant(self.tenant)
        from sites.models import Section
        self.assertEqual(Section.objects.count(), 1)

    def test_section_reorder(self):
        """PATCH /api/sites/sections/reorder/ bulk updates order."""
        client = Client(HTTP_HOST=self.domain)
        auth = self._auth()

        # Create two sections
        s1 = client.post(f"/api/pages/{self.page.id}/sections/", {"type": "hero", "order": 1}, content_type="application/json", **auth).json()
        s2 = client.post(f"/api/pages/{self.page.id}/sections/", {"type": "about", "order": 2}, content_type="application/json", **auth).json()

        # Reorder them
        resp = client.patch(
            f"/api/pages/{self.page.id}/sections/reorder/",
            [{"id": s1["id"], "order": 2}, {"id": s2["id"], "order": 1}],
            content_type="application/json", **auth
        )
        self.assertEqual(resp.status_code, 200)

        # Verify new order in db
        from django.db import connection
        connection.set_tenant(self.tenant)
        from sites.models import Section
        self.assertEqual(Section.objects.get(id=s1["id"]).order, 2)
        self.assertEqual(Section.objects.get(id=s2["id"]).order, 1)
