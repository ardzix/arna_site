from django.urls import path, include
from django.contrib import admin
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
   openapi.Info(
      title="ArnaSite Tenant API",
      default_version='v1',
      description="APIs for isolated tenant CMS data and Arna Storage integrations.",
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
   patterns=[
      path('api/tenants/current/', include('core.tenant_urls')),
      path('api/sites/', include('sites.urls')),
      path('api/storage/', include('storage.urls')),
      path('public/', include('sites.public_urls')),
   ],
)

urlpatterns = [
    path('site-admin/api/', include('config.admin_urls')),
    path('admin/', admin.site.urls),
    path('api/tenants/current/', include('core.tenant_urls')),
    path('api/sites/', include('sites.urls')),
    path('api/storage/', include('storage.urls')),
    # Public (no-auth) site rendering endpoint for tenant frontends
    path('public/', include('sites.public_urls')),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]
