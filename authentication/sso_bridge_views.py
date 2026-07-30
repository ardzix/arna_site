"""SSO authorization-code bridge for passkey login from ArnaSite FE."""
import base64
import hashlib
import json
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


SSO_STATE_COOKIE = "arnasite_sso_state"
SSO_VERIFIER_COOKIE = "arnasite_sso_code_verifier"


def _base64_url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _pkce_challenge(verifier: str) -> str:
    return _base64_url(hashlib.sha256(verifier.encode("ascii")).digest())


def _cookie_samesite():
    value = str(getattr(settings, "SSO_BRIDGE_COOKIE_SAMESITE", "None") or "None")
    return "None" if value.lower() == "none" else value


def _set_pkce_cookie(response: Response, name: str, value: str) -> None:
    response.set_cookie(
        name,
        value,
        max_age=getattr(settings, "SSO_BRIDGE_COOKIE_MAX_AGE", 300),
        secure=getattr(settings, "SSO_BRIDGE_COOKIE_SECURE", True),
        httponly=True,
        samesite=_cookie_samesite(),
    )


def _clear_pkce_cookies(response: Response) -> None:
    response.delete_cookie(
        SSO_STATE_COOKIE,
        samesite=_cookie_samesite(),
    )
    response.delete_cookie(
        SSO_VERIFIER_COOKIE,
        samesite=_cookie_samesite(),
    )


class SSOBridgeBeginView(APIView):
    """Create PKCE state and return the SSO login URL."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        state = secrets.token_urlsafe(48)
        code_verifier = secrets.token_urlsafe(64)
        params = urlencode(
            {
                "client_id": settings.SSO_BRIDGE_CLIENT_ID,
                "redirect_uri": settings.SSO_BRIDGE_REDIRECT_URI,
                "state": state,
                "code_challenge": _pkce_challenge(code_verifier),
                "code_challenge_method": "S256",
            }
        )
        web_base = settings.ARNA_SSO_WEB_BASE_URL.rstrip("/")
        response = Response({"redirect_url": f"{web_base}/login?{params}"})
        _set_pkce_cookie(response, SSO_STATE_COOKIE, state)
        _set_pkce_cookie(response, SSO_VERIFIER_COOKIE, code_verifier)
        return response


class SSOBridgeCallbackView(APIView):
    """Validate callback state and exchange the SSO authorization code."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        code = str(request.data.get("code") or "").strip()
        state = str(request.data.get("state") or "").strip()
        expected_state = request.COOKIES.get(SSO_STATE_COOKIE, "")
        code_verifier = request.COOKIES.get(SSO_VERIFIER_COOKIE, "")

        if (
            not code
            or not state
            or not expected_state
            or not code_verifier
            or not secrets.compare_digest(state, expected_state)
        ):
            response = Response(
                {"detail": "Invalid SSO callback state."},
                status=status.HTTP_400_BAD_REQUEST,
            )
            _clear_pkce_cookies(response)
            return response

        payload = {
            "grant_type": "authorization_code",
            "client_id": settings.SSO_BRIDGE_CLIENT_ID,
            "redirect_uri": settings.SSO_BRIDGE_REDIRECT_URI,
            "code": code,
            "code_verifier": code_verifier,
        }
        token_request = Request(
            f"{settings.ARNA_SSO_BASE_URL.rstrip('/')}/auth/sso/token/",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(
                token_request,
                timeout=getattr(settings, "SSO_BRIDGE_TOKEN_EXCHANGE_TIMEOUT", 10),
            ) as token_response:
                data = json.loads(token_response.read().decode("utf-8") or "{}")
        except HTTPError as exc:
            message = exc.read().decode("utf-8") or "SSO token exchange failed."
            response = Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)
            _clear_pkce_cookies(response)
            return response
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            response = Response(
                {"detail": f"SSO token exchange failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
            _clear_pkce_cookies(response)
            return response

        response = Response(data)
        _clear_pkce_cookies(response)
        return response
