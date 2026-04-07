from django.urls import path
from core.views import ApplyTemplateView

urlpatterns = [
    path("apply-template/", ApplyTemplateView.as_view(), name="apply-template"),
]
