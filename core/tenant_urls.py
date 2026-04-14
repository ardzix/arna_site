from django.urls import path
from core.views import TenantDetailView, ApplyTemplateView

urlpatterns = [
    path("",                TenantDetailView.as_view(),  name="tenant-detail"),
    path("apply-template/", ApplyTemplateView.as_view(), name="apply-template"),
]
