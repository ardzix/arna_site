import hashlib
from django.conf import settings
from django.core.cache import cache
import requests as http
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

class SSOUser:
    """
    Lightweight proxy object — no local DB row required.

    ✅ Stores ONLY primitive types (str, uuid str).
    ❌ Never store a live Django ORM instance here.
    Reason: Redis caches via pickle. Pickling a Django model instance
    (e.g. Tenant) either fails or returns stale DB state on unpickle,
    causing DatabaseError on the next request.
    """
    def __init__(self, user_id, email, org_id, tenant_schema, tenant_name):
        self.id = user_id
        self.email = email
        self.org_id = org_id
        self.tenant_schema = tenant_schema   # str — safe to pickle
        self.tenant_name = tenant_name       # str — safe to pickle
        self.is_authenticated = True
        self.is_anonymous = False

    def __str__(self):
        return self.email

class ArnaSSOAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None  # Let other auth classes try

        token = auth_header.split(" ", 1)[1]
        cache_key = f"sso_user:{hashlib.sha256(token.encode()).hexdigest()}"
        cached = cache.get(cache_key)

        if cached:
            return cached["user"], token

        # Validate token via /auth/me/
        sso_base = settings.ARNA_SSO_BASE_URL
        headers = {"Authorization": f"Bearer {token}"}

        try:
            me_resp = http.get(f"{sso_base}/auth/me/", headers=headers, timeout=5)
            me_resp.raise_for_status()
        except http.RequestException:
            raise AuthenticationFailed("Invalid or expired SSO token.")

        me_data = me_resp.json()

        # Get active organization
        try:
            org_resp = http.get(f"{sso_base}/organizations/current/",
                                headers=headers, timeout=5)
            org_resp.raise_for_status()
        except http.RequestException:
            raise AuthenticationFailed("No active SSO organization session.")

        org_data = org_resp.json()
        org_id = org_data["id"]

        # Resolve tenant — DB query runs against public schema
        from core.models import Tenant
        try:
            tenant = Tenant.objects.get(sso_organization_id=org_id)
        except Tenant.DoesNotExist:
            raise AuthenticationFailed(
                "This organization does not have an ArnaSite tenant."
            )

        # ✅ Pass only primitive strings — safe for Redis pickle
        user = SSOUser(
            user_id=me_data["id"],
            email=me_data["email"],
            org_id=org_id,
            tenant_schema=tenant.schema_name,  # str
            tenant_name=tenant.name,            # str
        )

        cache.set(cache_key, {"user": user}, timeout=settings.SSO_USER_CACHE_TTL)
        return user, token

    def authenticate_header(self, request):
        return "Bearer"
