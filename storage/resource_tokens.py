"""Exchange the authenticated human subject for a workspace-bound Storage token."""
from urllib.parse import urlsplit

import jwt
import requests
from django.conf import settings
from rest_framework.exceptions import APIException, PermissionDenied, AuthenticationFailed

from authentication.jwt_backends import get_cached_public_key


class StorageExchangeUnavailable(APIException):
    status_code = 503
    default_detail = "SSO Storage token exchange is unavailable. Retry shortly."


def storage_headers(request):
    subject = request.auth
    if not isinstance(subject, str) or not subject:
        raise AuthenticationFailed("A human SSO access token is required.")
    tenant = getattr(request, "tenant", None)
    org = str(getattr(request.user, "org_id", "") or "")
    tenant_id = str(getattr(tenant, "public_id", "") or "")
    if not org or not tenant_id or str(getattr(tenant, "sso_organization_id", "")) != org:
        raise PermissionDenied("Select the organization and tenant before accessing Storage.")
    base = settings.ARNA_SSO_BASE_URL.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or parsed.netloc != "sso.arnatech.id":
        raise StorageExchangeUnavailable()
    try:
        response = requests.post(base + "/v1/devices/resource-token/",
            headers={"Authorization": "Bearer " + subject}, json={"audience": "storage"},
            timeout=10, allow_redirects=False)
    except requests.RequestException:
        raise StorageExchangeUnavailable() from None
    if response.status_code == 401:
        raise AuthenticationFailed("SSO rejected the access token. Sign in again.")
    if response.status_code in (400, 403):
        raise PermissionDenied("Select this organization and tenant in SSO and ensure Storage permissions are assigned.")
    if response.status_code != 200:
        raise StorageExchangeUnavailable()
    try:
        token = response.json()["access_token"]
        claims = jwt.decode(token, get_cached_public_key(settings.SSO_JWT_PUBLIC_KEY_PATH),
            algorithms=["RS256"], audience="storage", issuer="https://sso.arnatech.id",
            options={"require": ["exp", "iat", "jti", "iss", "aud", "user_id", "org_id", "tenant_id", "token_type"]})
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise StorageExchangeUnavailable("SSO returned an invalid Storage resource token.") from None
    if (claims.get("principal_type") != "user" or claims["token_type"] != "access"
            or str(claims["user_id"]) != str(request.user.id)
            or claims["org_id"] != org or claims["tenant_id"] != tenant_id):
        raise PermissionDenied("SSO workspace differs from this site. Select this organization and tenant and retry.")
    return {"Authorization": "Bearer " + token}
