from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sites.views import SectionViewSet, ContentBlockViewSet, ListItemViewSet

router = DefaultRouter()
router.register(r'sections', SectionViewSet, basename='sections')
router.register(r'blocks', ContentBlockViewSet, basename='blocks')
router.register(r'items', ListItemViewSet, basename='items')

urlpatterns = [
    path('', include(router.urls)),
]
