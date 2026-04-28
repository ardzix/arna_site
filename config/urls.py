from django.urls import path, include, re_path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from authentication.jwt_backends import ArnaJWTAuthentication

schema_view = get_schema_view(
    openapi.Info(
        title="ArnaSite Tenant API",
        default_version='v1',
        description=(
            "CMS API untuk tenant ArnaSite.\n\n"
            "**Autentikasi:** Klik **Authorize** → masukkan token:\n\n"
            "`Bearer <jwt_token_dari_arna_sso>`\n\n"
            "- **GET**: cukup jadi member organisasi.\n"
            "- **POST/PATCH/DELETE**: butuh role `site_admin` atau `is_owner=true`."
        ),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    authentication_classes=(ArnaJWTAuthentication,),
    patterns=[
        path('api/tenant/',    include('core.tenant_urls')),
        path('api/domains/',   include('core.domain_urls')),
        path('api/templates/', include('core.template_urls')),
        path('api/pages/',     include('sites.urls')),
        path('api/files/',     include('storage.urls')),
        path('api/ai/',        include('ai_helper.urls')),
        path('api/public/',    include('sites.public_urls')),
    ],
)

urlpatterns = [
    path('api/tenant/',    include('core.tenant_urls')),
    path('api/domains/',   include('core.domain_urls')),
    path('api/templates/', include('core.template_urls')),
    path('api/pages/',     include('sites.urls')),
    path('api/files/',     include('storage.urls')),
    path('api/ai/',        include('ai_helper.urls')),
    path('api/public/',    include('sites.public_urls')),
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]
