"""Module for core.domain_urls."""
from django.urls import path
from core.website_context import PublicWebsiteContextView

from core.views import DomainListCreateView, DomainDetailView, PublicDomainResolveView

urlpatterns = [
    path("website-context/", PublicWebsiteContextView.as_view(), name="website-context"),
    path("resolve/",   PublicDomainResolveView.as_view(), name="domain-resolve"),
    path("",           DomainListCreateView.as_view(), name="domain-list"),
    path("<int:pk>/",  DomainDetailView.as_view(),     name="domain-detail"),
]
