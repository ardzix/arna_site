from django.urls import path
from sites.views import (
    PageListCreateView, PageDetailView, PageReorderView,
    SectionListCreateView, SectionDetailView, SectionReorderView,
    BlockListCreateView, BlockDetailView,
    ItemListCreateView, ItemDetailView,
)

# /api/pages/
# /api/pages/reorder/
# /api/pages/{page_id}/
# /api/pages/{page_id}/sections/
# /api/pages/{page_id}/sections/reorder/
# /api/pages/{page_id}/sections/{section_id}/
# /api/pages/{page_id}/sections/{section_id}/blocks/
# /api/pages/{page_id}/sections/{section_id}/blocks/{block_id}/
# /api/pages/{page_id}/sections/{section_id}/blocks/{block_id}/items/
# /api/pages/{page_id}/sections/{section_id}/blocks/{block_id}/items/{item_id}/

urlpatterns = [
    # Pages
    path("",
         PageListCreateView.as_view(), name="page-list"),
    path("reorder/",
         PageReorderView.as_view(), name="page-reorder"),
    path("<uuid:page_id>/",
         PageDetailView.as_view(), name="page-detail"),

    # Sections
    path("<uuid:page_id>/sections/",
         SectionListCreateView.as_view(), name="section-list"),
    path("<uuid:page_id>/sections/reorder/",
         SectionReorderView.as_view(), name="section-reorder"),
    path("<uuid:page_id>/sections/<uuid:section_id>/",
         SectionDetailView.as_view(), name="section-detail"),

    # Blocks
    path("<uuid:page_id>/sections/<uuid:section_id>/blocks/",
         BlockListCreateView.as_view(), name="block-list"),
    path("<uuid:page_id>/sections/<uuid:section_id>/blocks/<uuid:block_id>/",
         BlockDetailView.as_view(), name="block-detail"),

    # Items
    path("<uuid:page_id>/sections/<uuid:section_id>/blocks/<uuid:block_id>/items/",
         ItemListCreateView.as_view(), name="item-list"),
    path("<uuid:page_id>/sections/<uuid:section_id>/blocks/<uuid:block_id>/items/<uuid:item_id>/",
         ItemDetailView.as_view(), name="item-detail"),
]
