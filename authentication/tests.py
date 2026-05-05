import os
import uuid
import tempfile
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed

from authentication.jwt_backends import ArnaJWTAuthentication
from authentication.permissions import IsTenantAdmin, IsTenantOwner
from authentication.backends import SSOUser
from authentication.test_helpers import generate_rsa_keypair, make_jwt




class ArnaJWTAuthenticationTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_pem, cls.public_pem = generate_rsa_keypair()
        cls.other_private_pem, _ = generate_rsa_keypair()

    def setUp(self):
        # We patch the public key via override
        self.auth = ArnaJWTAuthentication()
        self.auth._public_key_override = self.public_pem.decode()

        self.user_id = uuid.uuid4()
        self.org_id = uuid.uuid4()
        
        # We need a mock DB tenant for the valid flow because it queries Tenant.objects
        # but to keep unit tests fast and independent of django_tenants DB setup
        # we can mock the Tenant resolution
        self.tenant_patch = patch('core.models.Tenant.objects.get')
        self.mock_tenant_get = self.tenant_patch.start()
        
        mock_tenant = MagicMock()
        mock_tenant.schema_name = 'tenant_mock'
        mock_tenant.name = 'Mock Tenant'
        self.mock_tenant_get.return_value = mock_tenant

        self.cache_patch = patch('authentication.jwt_backends.cache')
        self.mock_cache = self.cache_patch.start()
        self.mock_cache.get.return_value = None

    def tearDown(self):
        self.tenant_patch.stop()
        self.cache_patch.stop()

    def make_mock_request(self, auth_header=None):
        request = MagicMock()
        request.META = {}
        if auth_header is not None:
            request.META["HTTP_AUTHORIZATION"] = auth_header
        return request

    def test_no_authorization_header(self):
        req = self.make_mock_request()
        self.assertIsNone(self.auth.authenticate(req))

    def test_malformed_bearer_token(self):
        req = self.make_mock_request(auth_header="Token abcdef12345")
        self.assertIsNone(self.auth.authenticate(req))

    def test_invalid_jwt_signature(self):
        token = make_jwt(self.other_private_pem, self.user_id, self.org_id)
        req = self.make_mock_request(auth_header=f"Bearer {token}")
        with self.assertRaisesMessage(AuthenticationFailed, "Invalid or expired JWT token."):
            self.auth.authenticate(req)

    def test_expired_jwt_token(self):
        token = make_jwt(self.private_pem, self.user_id, self.org_id, expired=True)
        req = self.make_mock_request(auth_header=f"Bearer {token}")
        with self.assertRaisesMessage(AuthenticationFailed, "Invalid or expired JWT token."):
            self.auth.authenticate(req)

    def test_missing_user_id_claim(self):
        import jwt, datetime
        payload = {"org_id": str(self.org_id), "aud": "arnasite", "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}
        token = jwt.encode(payload, self.private_pem, algorithm="RS256")
        req = self.make_mock_request(auth_header=f"Bearer {token}")
        with self.assertRaisesMessage(AuthenticationFailed, "Invalid or expired JWT token."): # PyJWT will fail on options
            self.auth.authenticate(req)

    def test_missing_org_id_claim(self):
        import jwt, datetime
        payload = {"user_id": str(self.user_id), "aud": "arnasite", "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}
        token = jwt.encode(payload, self.private_pem, algorithm="RS256")
        req = self.make_mock_request(auth_header=f"Bearer {token}")
        with self.assertRaisesMessage(AuthenticationFailed, "Invalid or expired JWT token."): # PyJWT will fail on options
            self.auth.authenticate(req)
            
    def test_invalid_audience(self):
        token = make_jwt(self.private_pem, self.user_id, self.org_id, aud="some_other_service")
        req = self.make_mock_request(auth_header=f"Bearer {token}")
        with self.assertRaisesMessage(AuthenticationFailed, "Invalid or expired JWT token."):
            self.auth.authenticate(req)

    @patch('authentication.jwt_backends.settings.SSO_JWT_AUDIENCE', None)
    def test_invalid_audience_allowed_when_audience_check_disabled(self):
        token = make_jwt(self.private_pem, self.user_id, self.org_id, aud="some_other_service")
        req = self.make_mock_request(auth_header=f"Bearer {token}")
        result = self.auth.authenticate(req)
        self.assertIsNotNone(result)

    def test_org_id_no_matching_tenant(self):
        from core.models import Tenant
        self.mock_tenant_get.side_effect = Tenant.DoesNotExist
        token = make_jwt(self.private_pem, self.user_id, self.org_id)
        req = self.make_mock_request(auth_header=f"Bearer {token}")
        result = self.auth.authenticate(req)
        self.assertIsNotNone(result)
        user, _ = result
        self.assertEqual(user.tenant_schema, "")

    def test_valid_token_returns_ssouser(self):
        token = make_jwt(self.private_pem, self.user_id, self.org_id)
        req = self.make_mock_request(auth_header=f"Bearer {token}")
        
        result = self.auth.authenticate(req)
        self.assertIsNotNone(result)
        user, returned_token = result
        
        self.assertIsInstance(user, SSOUser)
        self.assertEqual(user.id, str(self.user_id))
        self.assertEqual(user.org_id, str(self.org_id))
        self.assertEqual(returned_token, token)
        
        self.mock_cache.set.assert_called_once()

    def test_ssouser_fields_populated(self):
        token = make_jwt(self.private_pem, self.user_id, self.org_id, roles=["site_admin"], is_owner=True)
        req = self.make_mock_request(auth_header=f"Bearer {token}")
        
        user, _ = self.auth.authenticate(req)
        self.assertIn("site_admin", user.roles)
        self.assertTrue(user.is_owner)

    def test_cache_hit_skips_decode(self):
        token = make_jwt(self.private_pem, self.user_id, self.org_id)
        req = self.make_mock_request(auth_header=f"Bearer {token}")
        
        cached_user = MagicMock()
        self.mock_cache.get.return_value = {"user": cached_user}
        
        # If cache hits, we don't query the DB, so we can stop our mock tenant get
        self.mock_tenant_get.side_effect = Exception("Should not hit DB or JWT decode!")
        
        user, returned_token = self.auth.authenticate(req)
        self.assertEqual(user, cached_user)

    def test_public_key_not_found(self):
        # Clear cache and create a new instance that fails to load key
        from authentication.jwt_backends import get_cached_public_key
        get_cached_public_key.cache_clear()
        
        with patch('authentication.jwt_backends.settings.SSO_JWT_PUBLIC_KEY_PATH', '/tmp/nonexistent_file.pem'):
            auth = ArnaJWTAuthentication()
            req = self.make_mock_request(auth_header="Bearer dummy")
            self.assertIsNone(auth.authenticate(req))

    def test_public_key_invalid_content(self):
        from authentication.jwt_backends import get_cached_public_key
        get_cached_public_key.cache_clear()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
            f.write("bukan pem sama sekali")
            fname = f.name
            
        try:
            with patch('authentication.jwt_backends.settings.SSO_JWT_PUBLIC_KEY_PATH', fname):
                auth = ArnaJWTAuthentication()
                req = self.make_mock_request(auth_header="Bearer dummy")
                self.assertIsNone(auth.authenticate(req))
        finally:
            os.unlink(fname)

    def test_public_key_contains_private_key(self):
        from authentication.jwt_backends import get_cached_public_key
        get_cached_public_key.cache_clear()
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
            f.write(self.private_pem)  # Write PRIVATE KEY instead of PUBLIC KEY
            fname = f.name
            
        try:
            with patch('authentication.jwt_backends.settings.SSO_JWT_PUBLIC_KEY_PATH', fname):
                auth = ArnaJWTAuthentication()
                req = self.make_mock_request(auth_header="Bearer dummy")
                # Should return None because it doesn't contain "PUBLIC KEY"
                self.assertIsNone(auth.authenticate(req))
        finally:
            os.unlink(fname)
            get_cached_public_key.cache_clear()

    def test_jwt_authenticate_header(self):
        auth = ArnaJWTAuthentication()
        self.assertEqual(auth.authenticate_header(None), "Bearer")

    def test_missing_both_claims(self):
        import datetime
        import jwt
        # Generate token with missing user_id AND org_id
        payload = {
            "email": "admin@arna.com",
            "roles": [],
            "permissions": [],
            "is_owner": False,
            "aud": "arnasite",
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        }
        token = jwt.encode(payload, self.private_pem, algorithm="RS256")
        req = self.make_mock_request(auth_header=f"Bearer {token}")
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(req)

    def test_get_cached_public_key_success(self):
        from authentication.jwt_backends import get_cached_public_key
        get_cached_public_key.cache_clear()
        
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
            f.write(self.public_pem)
            fname = f.name
            
        try:
            with patch('authentication.jwt_backends.settings.SSO_JWT_PUBLIC_KEY_PATH', fname):
                content = get_cached_public_key(fname)
                self.assertEqual(content, self.public_pem.decode())
        finally:
            os.unlink(fname)
            get_cached_public_key.cache_clear()

    @patch('builtins.open', side_effect=Exception("Generic Error"))
    def test_get_cached_public_key_exception(self, mock_open):
        from authentication.jwt_backends import get_cached_public_key
        get_cached_public_key.cache_clear()
        self.assertIsNone(get_cached_public_key("dummy"))
        get_cached_public_key.cache_clear()
        
        
class PermissionTest(TestCase):
    def test_tenant_admin_with_site_admin_role(self):
        perm = IsTenantAdmin()
        req = MagicMock()
        req.user = MagicMock()
        req.user.roles = ["user", "site_admin"]
        self.assertTrue(perm.has_permission(req, MagicMock()))

    def test_tenant_admin_without_role(self):
        perm = IsTenantAdmin()
        req = MagicMock()
        req.user = MagicMock()
        req.user.roles = ["user"]
        self.assertFalse(perm.has_permission(req, MagicMock()))

    def test_tenant_admin_missing_roles_attr(self):
        perm = IsTenantAdmin()
        req = MagicMock()
        req.user = object() # No roles attr
        self.assertFalse(perm.has_permission(req, MagicMock()))

    def test_tenant_owner_is_owner_true(self):
        perm = IsTenantOwner()
        req = MagicMock()
        req.user = MagicMock()
        req.user.is_owner = True
        self.assertTrue(perm.has_permission(req, MagicMock()))

    def test_tenant_owner_is_owner_false(self):
        perm = IsTenantOwner()
        req = MagicMock()
        req.user = MagicMock()
        req.user.is_owner = False
        self.assertFalse(perm.has_permission(req, MagicMock()))

    def test_tenant_owner_missing_attr(self):
        perm = IsTenantOwner()
        req = MagicMock()
        req.user = object() # No is_owner attr
        self.assertFalse(perm.has_permission(req, MagicMock()))

    def test_tenant_member_no_connection_tenant(self):
        from authentication.permissions import IsTenantMember
        from authentication.backends import SSOUser
        from unittest.mock import patch, MagicMock
        perm = IsTenantMember()
        req = MagicMock()
        req.user = SSOUser(user_id='1', email='a@a.com', org_id='o1',
                           tenant_schema='tenant_x', tenant_name='X')
        with patch('authentication.permissions.connection') as mock_conn:
            mock_conn.tenant = None
            result = perm.has_permission(req, MagicMock())
        self.assertFalse(result)

    def test_sso_auth_user_cannot_access_admin_without_roles(self):
        """Regression: SSO user without site_admin role must fail IsTenantAdmin."""
        from authentication.permissions import IsTenantAdmin
        from authentication.backends import SSOUser
        user = SSOUser(
            user_id='u1', email='user@arna.com', org_id='o1',
            tenant_schema='tenant_x', tenant_name='X',
            roles=[],  # Empty roles
            permissions=[],
            is_owner=False
        )
        perm = IsTenantAdmin()
        req = MagicMock()
        req.user = user
        self.assertFalse(perm.has_permission(req, MagicMock()))

    def test_tenant_member_no_tenant_schema_attr(self):
        from authentication.permissions import IsTenantMember
        perm = IsTenantMember()
        req = MagicMock()
        req.user = object() # No tenant_schema
        self.assertFalse(perm.has_permission(req, MagicMock()))
