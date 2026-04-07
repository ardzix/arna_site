from django.urls import path
from sites.views import BlockDetailView, ItemListCreateView

urlpatterns = [
    path("<uuid:pk>/", BlockDetailView.as_view(), name="block-detail"),
    path("<uuid:block_id>/items/", ItemListCreateView.as_view(), name="item-list"),
]
