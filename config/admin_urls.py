from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from authentication.jwt_backends import ArnaJWTAuthentication
from sites.admin_views import (
    AdminSectionViewSet,
    AdminContentBlockViewSet,
    AdminListItemViewSet,
    AdminSectionReorderView,
    AdminMediaReferenceViewSet,
    AdminApplyTemplateView,
)

router = DefaultRouter()
router.register(r'sections', AdminSectionViewSet, basename='admin-sections')
router.register(r'blocks', AdminContentBlockViewSet, basename='admin-blocks')
router.register(r'items', AdminListItemViewSet, basename='admin-items')
router.register(r'storage', AdminMediaReferenceViewSet, basename='admin-storage')

schema_view = get_schema_view(
   openapi.Info(
      title="ArnaSite Site Admin API",
      default_version='v1',
      description="API endpoints for tenant administrators to manage website content.",
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
   authentication_classes=(ArnaJWTAuthentication,),
    patterns=[
        path('sections/reorder/', AdminSectionReorderView.as_view(), name='admin-section-reorder-docs'),
        path('tenants/current/apply-template/', AdminApplyTemplateView.as_view(), name='admin-apply-template-docs'),
        path('', include(router.urls)),
    ],
)

urlpatterns = [
    path('sections/reorder/', AdminSectionReorderView.as_view(), name='admin-section-reorder'),
    path('tenants/current/apply-template/', AdminApplyTemplateView.as_view(), name='admin-apply-template'),
    path('', include(router.urls)),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-admin-swagger-ui'),
]
