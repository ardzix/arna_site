from django.urls import path
from core.views import DomainListCreateView, DomainDetailView, PublicDomainResolveView

urlpatterns = [
    path("resolve/",   PublicDomainResolveView.as_view(), name="domain-resolve"),
    path("",           DomainListCreateView.as_view(), name="domain-list"),
    path("<int:pk>/",  DomainDetailView.as_view(),     name="domain-detail"),
]
