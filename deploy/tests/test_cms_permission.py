"""CMS permission delegation must never use the shared schema as authority."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from authentication.permissions import IsTenantAdmin, IsTenantMember, IsTenantOwner


class CmsPermissionTests(unittest.TestCase):
    def request(self, **changes):
        values = dict(is_authenticated=True, roles=[], permissions=['arnasite.cms.manage'],
                      org_id='org-a', tenant_schema='pool_shared', is_owner=False)
        values.update(changes)
        return SimpleNamespace(user=SimpleNamespace(**values), headers={'X-Arna-Organization-ID': 'org-a'})

    def check(self, request, tenant_org='org-a'):
        tenant = SimpleNamespace(sso_organization_id=tenant_org, schema_name='pool_shared')
        with patch('authentication.permissions.connection', SimpleNamespace(tenant=tenant)):
            return IsTenantAdmin().has_permission(request, None)

    def test_cms_grant_in_current_organization(self):
        self.assertTrue(self.check(self.request()))

    def test_grant_cannot_cross_organization_even_in_same_pool(self):
        self.assertFalse(self.check(self.request(), tenant_org='org-b'))

    def test_missing_org_never_falls_back_to_shared_schema(self):
        for request, tenant_org in [(self.request(org_id=''), 'org-a'), (self.request(), '')]:
            with self.subTest(tenant_org=tenant_org):
                self.assertFalse(self.check(request, tenant_org))

    def test_legacy_member_fallback_does_not_enable_new_admin_grant(self):
        request = self.request(org_id='')
        tenant = SimpleNamespace(sso_organization_id='', schema_name='pool_shared')
        with patch('authentication.permissions.connection', SimpleNamespace(tenant=tenant)):
            self.assertTrue(IsTenantMember().has_permission(request, None))
            self.assertFalse(IsTenantAdmin().has_permission(request, None))

    def test_missing_tenant_denied(self):
        with patch('authentication.permissions.connection', SimpleNamespace(tenant=None)):
            self.assertFalse(IsTenantAdmin().has_permission(self.request(), None))

    def test_permissions_must_be_array_and_exact_key(self):
        for grants in ['arnasite.cms.manage', ['prefix-arnasite.cms.manage'], ['crm.manage'], [], None]:
            with self.subTest(grants=grants):
                self.assertFalse(self.check(self.request(permissions=grants)))

    def test_anonymous_cannot_use_cms_grant(self):
        self.assertFalse(self.check(self.request(is_authenticated=False)))

    def test_headers_cannot_supply_membership(self):
        self.assertFalse(self.check(self.request(org_id='org-b')))

    def test_existing_site_admin_role_is_preserved(self):
        self.assertTrue(self.check(self.request(roles=['site_admin'], permissions=[])))

    def test_existing_owner_permission_is_preserved(self):
        self.assertTrue(IsTenantOwner().has_permission(self.request(is_owner=True), None))


if __name__ == '__main__':
    unittest.main()
