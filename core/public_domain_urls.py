"""Module for core.public_domain_urls."""
from django.urls import path
from core.website_context import PublicWebsiteContextView

from core.views import PublicDomainResolveView

urlpatterns = [
    path("website-context/", PublicWebsiteContextView.as_view(), name="public-website-context"),
    path("resolve/", PublicDomainResolveView.as_view(), name="public-domain-resolve"),
]

