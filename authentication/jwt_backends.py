import hashlib
import jwt
from django.conf import settings
from django.core.cache import cache
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from authentication.backends import SSOUser
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_cached_public_key(key_path):
    try:
        with open(key_path, 'r') as f:
            content = f.read()
            if "PUBLIC KEY" not in content:
                logger.critical("CRITICAL: SSO_JWT_PUBLIC_KEY_PATH '%s' does not contain a PUBLIC KEY. Admin API authentication is DISABLED.", key_path)
                return None
            return content
    except FileNotFoundError:
        logger.critical("CRITICAL: SSO_JWT_PUBLIC_KEY_PATH not found at '%s'. Admin API authentication is DISABLED.", key_path)
        return None
    except Exception as e:
        logger.critical("CRITICAL: Unexpected error loading public key at '%s': %s", key_path, str(e))
        return None

class ArnaJWTAuthentication(BaseAuthentication):
    """
    Authenticates against a JWT token by decoding it locally using a public key.
    This is faster than calling the /auth/me endpoint, but may serve stale data
    if roles/permissions change before the token expires.

    Ideal for high-throughput admin endpoints where performance is critical.
    """
    @property
    def public_key(self):
        if hasattr(self, '_public_key_override'):
             return self._public_key_override
        return get_cached_public_key(settings.SSO_JWT_PUBLIC_KEY_PATH)

    def authenticate(self, request):
        if not self.public_key:
            # If the public key could not be loaded, this backend is disabled.
            return None

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ", 1)[1]
        cache_key = f"sso_jwt_user:{hashlib.sha256(token.encode()).hexdigest()}"

        try:
            cached = cache.get(cache_key)
        except Exception:
            cached = None

        if cached:
            return cached["user"], token

        try:
            claims = jwt.decode(
                token,
                self.public_key,
                algorithms=[settings.SSO_JWT_ALGORITHM],
                options={
                    "require": ["exp", "user_id"],
                    "verify_aud": False,
                },
            )
        except jwt.PyJWTError as e:
            raise AuthenticationFailed(f"Invalid or expired JWT token: {e}")

        user_id = claims.get("user_id")
        org_id = claims.get("org_id")

        # Resolve tenant from organization ID.
        # Return None (anonymous) instead of raising when tenant doesn't exist yet —
        # e.g. during POST /tenants/register/ the tenant hasn't been created yet.
        # Views that require a tenant (IsTenantMember etc.) will reject the request anyway.
        from core.models import Tenant
        try:
            tenant = Tenant.objects.get(sso_organization_id=org_id)
        except Tenant.DoesNotExist:
            return None

        user = SSOUser(
            user_id=user_id,
            email=claims.get("email", ""),
            org_id=org_id,
            tenant_schema=tenant.schema_name,
            tenant_name=tenant.name,
            roles=claims.get("roles", []),
            permissions=claims.get("permissions", []),
            is_owner=claims.get("is_owner", False)
        )

        try:
            cache.set(cache_key, {"user": user}, timeout=60)
        except Exception:
            pass  # Redis down — proceed without caching

        return user, token

    def authenticate_header(self, request):
        return "Bearer"
