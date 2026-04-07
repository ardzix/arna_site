from django.urls import path
from sites.views import ItemDetailView

urlpatterns = [
    path("<uuid:pk>/", ItemDetailView.as_view(), name="item-detail"),
]
