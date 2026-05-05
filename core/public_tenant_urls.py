from django.urls import path
from core.views import TenantMyListView

urlpatterns = [
    path("", TenantMyListView.as_view(), name="tenant-my-list"),
]

