from django.urls import path
from core.views import DomainListCreateView, DomainDetailView

urlpatterns = [
    path("",           DomainListCreateView.as_view(), name="domain-list"),
    path("<int:pk>/",  DomainDetailView.as_view(),     name="domain-detail"),
]
