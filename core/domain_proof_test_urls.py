from django.urls import path
from core.domain_proof_views import DomainOwnershipProofView, DomainOwnershipCommitView
urlpatterns = [
    path("domains/<int:pk>/ownership/proof/", DomainOwnershipProofView.as_view()),
    path("domains/<int:pk>/ownership/commit/", DomainOwnershipCommitView.as_view()),
]
