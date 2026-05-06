from django.urls import path
from core.views import (
    TenantDetailView,
    ApplyTemplateView,
    TenantEntitlementRuntimeView,
    TenantPremiumCheckoutView,
)

urlpatterns = [
    path("",                     TenantDetailView.as_view(),           name="tenant-detail"),
    path("apply-template/",      ApplyTemplateView.as_view(),          name="apply-template"),
    path("entitlements/runtime/", TenantEntitlementRuntimeView.as_view(), name="tenant-entitlements-runtime"),
    path("checkout/premium/",    TenantPremiumCheckoutView.as_view(),  name="tenant-checkout-premium"),
]
