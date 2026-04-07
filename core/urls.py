from django.urls import path
from core.views import TemplateListView, TemplateDetailView

urlpatterns = [
    path("", TemplateListView.as_view(), name="template-list"),
    path("<uuid:pk>/", TemplateDetailView.as_view(), name="template-detail"),
]
