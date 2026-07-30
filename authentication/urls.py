"""Public authentication bridge URLs for ArnaSite."""
from django.urls import path

from authentication.sso_bridge_views import SSOBridgeBeginView, SSOBridgeCallbackView


urlpatterns = [
    path("sso/bridge/begin/", SSOBridgeBeginView.as_view(), name="sso-bridge-begin"),
    path("sso/bridge/callback/", SSOBridgeCallbackView.as_view(), name="sso-bridge-callback"),
]
