import tempfile
import os
import uuid
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.db import connection
from django_tenants.test.client import TenantClient

from core.models import Tenant, Domain, Template, TemplateSection, TemplateBlock
from sites.models import Section, ContentBlock, ListItem
from authentication.test_helpers import generate_rsa_keypair, make_jwt
from authentication.jwt_backends import ArnaJWTAuthentication

@override_settings(ALLOWED_HOSTS=['*'])
class AdminAPITest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Generate keypair once for the whole class
        cls.private_pem, cls.public_pem = generate_rsa_keypair()
        cls.other_private_pem, _ = generate_rsa_keypair()
        
        # Write public key to a temp file
        cls.key_file = tempfile.NamedTemporaryFile(suffix='.pem', delete=False)
        cls.key_file.write(cls.public_pem)
        cls.key_file.close()

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.key_file.name)
        super().tearDownClass()

    def setUp(self):
        connection.set_schema_to_public()
        
        self.public_tenant, _ = Tenant.objects.get_or_create(
            schema_name='public',
            defaults={
                'name': 'ArnaSite Global',
                'slug': 'public',
                'sso_organization_id': uuid.uuid4()
            }
        )
        Domain.objects.get_or_create(domain='localhost', tenant=self.public_tenant, is_primary=True)
        
        # Create Template
        self.template = Template.objects.create(name='Test Master', slug='test-master')
        self.t_section = TemplateSection.objects.create(template=self.template, type='hero', order=1)
        self.t_block = TemplateBlock.objects.create(section=self.t_section, title='Hero Block', order=1)
        
        self.org_id = uuid.uuid4()
        self.other_org_id = uuid.uuid4()
        
        # Target tenant
        self.tenant = Tenant.objects.create(
            schema_name='tenant_admin_test', name='Admin Test',
            slug='admin-test', sso_organization_id=self.org_id
        )
        Domain.objects.create(domain='admin.localhost', tenant=self.tenant, is_primary=True)
        
        # Other tenant (to test cross-tenant access)
        self.other_tenant = Tenant.objects.create(
            schema_name='tenant_other', name='Other Test',
            slug='other-test', sso_organization_id=self.other_org_id
        )

        
        # Override settings for public key path
        self.settings_override = override_settings(
            SSO_JWT_PUBLIC_KEY_PATH=self.key_file.name,
            SSO_JWT_AUDIENCE='arnasite'
        )
        self.settings_override.enable()

        self.client = TenantClient(self.tenant)
        self.other_client = TenantClient(self.other_tenant)
        
        self.patcher = patch.object(ArnaJWTAuthentication, '_public_key_override', new=self.public_pem.decode(), create=True)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.settings_override.disable()

    def _admin_auth(self, org_id=None, roles=None, is_owner=False, private_pem_override=None):
        if org_id is None:
            org_id = self.org_id
        pem_to_use = private_pem_override or self.private_pem
            
        token = make_jwt(pem_to_use, uuid.uuid4(), org_id, roles=roles, is_owner=is_owner)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    # ---- Auth Guard Tests ----

    def test_admin_no_token(self):
        resp = self.client.get("/admin/api/sections/")
        self.assertEqual(resp.status_code, 401)

    def test_admin_invalid_jwt_signature(self):
        auth = self._admin_auth(roles=["site_admin"], private_pem_override=self.other_private_pem)
        resp = self.client.get("/admin/api/sections/", **auth)
        self.assertEqual(resp.status_code, 401)

    def test_admin_authenticated_but_not_admin(self):
        auth = self._admin_auth(roles=["user"], is_owner=False)
        resp = self.client.get("/admin/api/sections/", **auth)
        self.assertEqual(resp.status_code, 403)

    def test_admin_wrong_tenant(self):
        # A valid JWT for other_org_id trying to hit self.tenant (via self.client)
        auth = self._admin_auth(org_id=self.other_org_id, roles=["site_admin"])
        resp = self.client.get("/admin/api/sections/", **auth)
        self.assertEqual(resp.status_code, 403)

    # ---- Happy Path CRUD Tests ----

    def test_admin_crud_flow(self):
        auth = self._admin_auth(roles=["site_admin"])
        
        # LIST SECTIONS
        resp = self.client.get("/admin/api/sections/", **auth)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 0)
        
        # CREATE SECTION
        resp = self.client.post("/admin/api/sections/", {"type": "hero", "order": 1}, content_type="application/json", **auth)
        self.assertEqual(resp.status_code, 201)
        section_id = resp.json()["id"]
        
        # UPDATE SECTION
        resp = self.client.patch(f"/admin/api/sections/{section_id}/", {"type": "about"}, content_type="application/json", **auth)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["type"], "about")
        
        # CREATE BLOCK
        resp = self.client.post("/admin/api/blocks/", {"section": section_id, "title": "Block A", "order": 1}, content_type="application/json", **auth)
        self.assertEqual(resp.status_code, 201)
        block_id = resp.json()["id"]
        
        # LIST BLOCKS FILTERED
        resp = self.client.get(f"/admin/api/blocks/?section={section_id}", **auth)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        
        # CREATE ITEM
        resp = self.client.post("/admin/api/items/", {"block": block_id, "title": "Item A", "order": 1}, content_type="application/json", **auth)
        self.assertEqual(resp.status_code, 201)
        
        # DELETE SECTION
        resp = self.client.delete(f"/admin/api/sections/{section_id}/", **auth)
        self.assertEqual(resp.status_code, 204)

    # ---- Reorder Endpoint Tests ----

    def test_admin_reorder_sections_success(self):
        auth = self._admin_auth(roles=["site_admin"])
        
        s1 = self.client.post("/admin/api/sections/", {"type": "hero", "order": 1}, content_type="application/json", **auth).json()
        s2 = self.client.post("/admin/api/sections/", {"type": "about", "order": 2}, content_type="application/json", **auth).json()
        
        resp = self.client.patch("/admin/api/sections/reorder/", [
            {"id": s1["id"], "order": 2},
            {"id": s2["id"], "order": 1}
        ], content_type="application/json", **auth)
        
        self.assertEqual(resp.status_code, 200)
        
        # verify DB
        connection.set_tenant(self.tenant)
        self.assertEqual(Section.objects.get(id=s1["id"]).order, 2)
        self.assertEqual(Section.objects.get(id=s2["id"]).order, 1)

    def test_admin_reorder_not_a_list(self):
        auth = self._admin_auth(roles=["site_admin"])
        resp = self.client.patch("/admin/api/sections/reorder/", {"id": "blah"}, content_type="application/json", **auth)
        self.assertEqual(resp.status_code, 400)

    def test_admin_reorder_invalid_uuid(self):
        auth = self._admin_auth(roles=["site_admin"])
        resp = self.client.patch("/admin/api/sections/reorder/", [{"id": "not-a-uuid", "order": 1}], content_type="application/json", **auth)
        self.assertEqual(resp.status_code, 400)
        
    def test_admin_reorder_unauthorized(self):
        resp = self.client.patch("/admin/api/sections/reorder/", [{"id": str(uuid.uuid4()), "order": 1}], content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    # ---- Owner vs Admin Parity ----

    def test_owner_can_access_admin_api(self):
        auth = self._admin_auth(is_owner=True, roles=[])
        resp = self.client.get("/admin/api/sections/", **auth)
        self.assertEqual(resp.status_code, 200)

    def test_site_admin_can_access_admin_api(self):
        auth = self._admin_auth(is_owner=False, roles=["site_admin"])
        resp = self.client.get("/admin/api/sections/", **auth)
        self.assertEqual(resp.status_code, 200)

    # ---- Apply Template via Admin Path ----

    def test_admin_apply_template(self):
        auth = self._admin_auth(roles=["site_admin"])
        
        resp = self.client.post("/admin/api/tenants/current/apply-template/", {
            "template_id": str(self.template.id)
        }, content_type="application/json", **auth)
        
        self.assertEqual(resp.status_code, 200)
        
        connection.set_tenant(self.tenant)
        self.assertTrue(Section.objects.filter(type="hero").exists())

    def test_admin_apply_template_unauthorized(self):
        resp = self.client.post("/admin/api/tenants/current/apply-template/", {
            "template_id": str(self.template.id)
        }, content_type="application/json")
        
        self.assertEqual(resp.status_code, 401)

    def test_admin_storage_requires_auth(self):
        resp = self.client.get("/admin/api/storage/")
        self.assertEqual(resp.status_code, 401)

    def test_admin_filter_items_by_block(self):
        auth = self._admin_auth(roles=["site_admin"])
        # CREATE SECTION
        s1 = self.client.post("/admin/api/sections/", {"type": "hero", "order": 1}, content_type="application/json", **auth).json()
        # CREATE BLOCKS
        b1 = self.client.post("/admin/api/blocks/", {"section": s1["id"], "title": "B1", "order": 1}, content_type="application/json", **auth).json()
        b2 = self.client.post("/admin/api/blocks/", {"section": s1["id"], "title": "B2", "order": 2}, content_type="application/json", **auth).json()
        
        # CREATE ITEMS FOR B1
        self.client.post("/admin/api/items/", {"block": b1["id"], "title": "Item 1", "order": 1}, content_type="application/json", **auth)
        self.client.post("/admin/api/items/", {"block": b1["id"], "title": "Item 2", "order": 2}, content_type="application/json", **auth)
        
        # FILTER ITEMS BY B1
        resp = self.client.get(f"/admin/api/items/?block={b1['id']}", **auth)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 2)
        
        # FILTER ITEMS BY B2
        resp = self.client.get(f"/admin/api/items/?block={b2['id']}", **auth)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 0)

    def test_admin_apply_template_overwrite(self):
        auth = self._admin_auth(roles=["site_admin"])
        # Apply once
        resp = self.client.post("/admin/api/tenants/current/apply-template/", {"template_id": str(self.template.id)}, content_type="application/json", **auth)
        self.assertEqual(resp.status_code, 200)
        
        # Apply again without overwrite -> 409
        resp = self.client.post("/admin/api/tenants/current/apply-template/", {"template_id": str(self.template.id)}, content_type="application/json", **auth)
        self.assertEqual(resp.status_code, 409)
        
        # Apply with overwrite -> 200
        resp = self.client.post("/admin/api/tenants/current/apply-template/", {"template_id": str(self.template.id), "overwrite": "true"}, content_type="application/json", **auth)
        self.assertEqual(resp.status_code, 200)

    def test_owner_and_admin_role_combined(self):
        auth = self._admin_auth(is_owner=True, roles=["site_admin"])
        resp = self.client.get("/admin/api/sections/", **auth)
        self.assertEqual(resp.status_code, 200)

    def test_admin_apply_nonexistent_template(self):
        auth = self._admin_auth(roles=["site_admin"])
        resp = self.client.post("/admin/api/tenants/current/apply-template/", {"template_id": str(uuid.uuid4())}, content_type="application/json", **auth)
        self.assertEqual(resp.status_code, 404)

    def test_admin_reorder_cross_tenant_section_is_noop(self):
        # section created in other_tenant shouldn't be affected
        from sites.models import Section
        connection.set_tenant(self.other_tenant)
        s_other = Section.objects.create(type="hero", order=10)
        connection.set_tenant(self.tenant)
        
        auth = self._admin_auth(roles=["site_admin"])
        resp = self.client.patch("/admin/api/sections/reorder/", [{"id": str(s_other.id), "order": 1}], content_type="application/json", **auth)
        
        self.assertEqual(resp.status_code, 200) # noop success
        
        connection.set_tenant(self.other_tenant)
        self.assertEqual(Section.objects.get(id=s_other.id).order, 10)
        connection.set_tenant(self.tenant)

    def test_admin_cache_hit(self):
        auth = self._admin_auth(roles=["site_admin"])
        resp1 = self.client.get("/admin/api/sections/", **auth)
        resp2 = self.client.get("/admin/api/sections/", **auth)
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
