from django.urls import path
from core.views import (
    TenantTemplateListCreateView,
    TenantTemplateDetailView,
    TenantTemplatePublishView,
)

urlpatterns = [
    path("",                     TenantTemplateListCreateView.as_view(), name="template-list"),
    path("<uuid:pk>/",           TenantTemplateDetailView.as_view(),     name="template-detail"),
    path("<uuid:pk>/publish/",   TenantTemplatePublishView.as_view(),    name="template-publish"),
]
