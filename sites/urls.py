from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sites.views import SectionViewSet, ContentBlockViewSet, ListItemViewSet, SectionReorderView

router = DefaultRouter()
router.register(r'sections', SectionViewSet, basename='sections')
router.register(r'blocks', ContentBlockViewSet, basename='blocks')
router.register(r'items', ListItemViewSet, basename='items')

urlpatterns = [
    path('sections/reorder/', SectionReorderView.as_view(), name='section-reorder'),
    path('', include(router.urls)),
    path('blocks/', include('sites.block_urls')),
    path('items/', include('sites.item_urls')),
]
