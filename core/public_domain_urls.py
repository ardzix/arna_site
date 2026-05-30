"""Module for core.public_domain_urls."""
from django.urls import path

from core.views import PublicDomainResolveView

urlpatterns = [
    path("resolve/", PublicDomainResolveView.as_view(), name="public-domain-resolve"),
]

