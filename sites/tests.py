from django.test import TestCase, override_settings
from django_tenants.test.client import TenantClient
from unittest.mock import patch
import uuid
from core.models import Tenant, Domain


def _make_auth_mock(org_id_str):
    class MockMe:
        def json(self): return {"id": str(uuid.uuid4()), "email": "owner@arna.com"}
        def raise_for_status(self): pass

    class MockOrg:
        def json(self): return {"id": org_id_str}
        def raise_for_status(self): pass

    def side_effect(url, *args, **kwargs):
        if "auth/me" in url: return MockMe()
        elif "organizations/current" in url: return MockOrg()
        raise Exception(f"Unmocked URL: {url}")

    return side_effect

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
        Domain.objects.create(domain='sites.localhost', tenant=self.tenant, is_primary=True)

    @patch('authentication.backends.http.get')
    def test_tenant_crud_operations(self, mock_get):
        """Create, list, and verify tenant-scoped sections via the API."""
        mock_get.side_effect = _make_auth_mock(str(self.org_id))

        client = TenantClient(self.tenant)
        auth = {"HTTP_AUTHORIZATION": "Bearer valid_token"}

        # POST - Create Section
        resp_post = client.post(
            "/api/sites/sections/",
            {"type": "hero", "order": 1, "is_active": True},
            content_type="application/json", **auth
        )
        self.assertEqual(resp_post.status_code, 201,
                         f"Create failed: {resp_post.content}")

        section_id = resp_post.json()["id"]

        # GET - List Sections
        resp_get = client.get("/api/sites/sections/", **auth)
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(len(resp_get.json()), 1)

        # PATCH - Update Section
        resp_patch = client.patch(
            f"/api/sites/sections/{section_id}/",
            {"type": "about"},
            content_type="application/json", **auth
        )
        self.assertEqual(resp_patch.status_code, 200)
        self.assertEqual(resp_patch.json()["type"], "about")

        # DELETE - Remove Section
        resp_delete = client.delete(f"/api/sites/sections/{section_id}/", **auth)
        self.assertEqual(resp_delete.status_code, 204)

        # Confirm deletion
        resp_get2 = client.get("/api/sites/sections/", **auth)
        self.assertEqual(len(resp_get2.json()), 0)

    @patch('authentication.backends.http.get')
    def test_filter_blocks_by_section(self, mock_get):
        """GET /api/sites/blocks/?section=<id> only returns blocks for that section."""
        mock_get.side_effect = _make_auth_mock(str(self.org_id))
        client = TenantClient(self.tenant)
        auth = {"HTTP_AUTHORIZATION": "Bearer valid_token"}

        # Create two sections
        s1 = client.post("/api/sites/sections/",
                         {"type": "hero", "order": 1},
                         content_type="application/json", **auth).json()
        s2 = client.post("/api/sites/sections/",
                         {"type": "about", "order": 2},
                         content_type="application/json", **auth).json()

        # Create a block under s1 only
        client.post("/api/sites/blocks/",
                    {"section": s1["id"], "order": 1},
                    content_type="application/json", **auth)

        # Filter by s1 — expect 1
        resp = client.get(f"/api/sites/blocks/?section={s1['id']}", **auth)
        self.assertEqual(len(resp.json()), 1)

        # Filter by s2 — expect 0
        resp2 = client.get(f"/api/sites/blocks/?section={s2['id']}", **auth)
        self.assertEqual(len(resp2.json()), 0)

    @patch('authentication.backends.http.get')
    def test_public_site_view_no_auth_required(self, mock_get):
        """GET /public/site/ must return 200 without any auth header."""
        mock_get.side_effect = _make_auth_mock(str(self.org_id))
        client = TenantClient(self.tenant)

        resp = client.get("/public/site/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("tenant", data)
        self.assertIn("sections", data)
        self.assertEqual(data["tenant"]["slug"], "sites-test")

    @patch('authentication.backends.http.get')
    def test_schema_isolation(self, mock_get):
        """Direct DB check: sections only exist in the correct tenant schema."""
        mock_get.side_effect = _make_auth_mock(str(self.org_id))
        client = TenantClient(self.tenant)
        auth = {"HTTP_AUTHORIZATION": "Bearer valid_token"}

        client.post("/api/sites/sections/",
                    {"type": "hero", "order": 1},
                    content_type="application/json", **auth)

        from django.db import connection
        connection.set_tenant(self.tenant)
        from sites.models import Section
        self.assertEqual(Section.objects.count(), 1)

    @patch('authentication.backends.http.get')
    def test_section_reorder(self, mock_get):
        """PATCH /api/sites/sections/reorder/ bulk updates order."""
        mock_get.side_effect = _make_auth_mock(str(self.org_id))
        client = TenantClient(self.tenant)
        auth = {"HTTP_AUTHORIZATION": "Bearer valid_token"}

        # Create two sections
        s1 = client.post("/api/sites/sections/", {"type": "hero", "order": 1}, content_type="application/json", **auth).json()
        s2 = client.post("/api/sites/sections/", {"type": "about", "order": 2}, content_type="application/json", **auth).json()

        # Reorder them
        resp = client.patch(
            "/api/sites/sections/reorder/",
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
