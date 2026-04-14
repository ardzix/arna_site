from django.urls import path
from core.views import TenantRegisterView

urlpatterns = [
    path("", TenantRegisterView.as_view(), name="tenant-register"),
]
