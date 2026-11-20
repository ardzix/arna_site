"""Module for core.domain_urls."""
from django.urls import path
from core.website_context import PublicWebsiteContextView

from core.views import DomainListCreateView, DomainDetailView, PublicDomainResolveView

from core.domain_proof_views import DomainOwnershipProofView, DomainOwnershipCommitView

urlpatterns = [
    path("<int:pk>/ownership/proof/", DomainOwnershipProofView.as_view(), name="domain-ownership-proof"),
    path("<int:pk>/ownership/commit/", DomainOwnershipCommitView.as_view(), name="domain-ownership-commit"),
    path("website-context/", PublicWebsiteContextView.as_view(), name="website-context"),
    path("resolve/",   PublicDomainResolveView.as_view(), name="domain-resolve"),
    path("",           DomainListCreateView.as_view(), name="domain-list"),
    path("<int:pk>/",  DomainDetailView.as_view(),     name="domain-detail"),
]
