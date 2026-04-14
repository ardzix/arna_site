from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from authentication.jwt_backends import ArnaJWTAuthentication

schema_view = get_schema_view(
    openapi.Info(
        title="ArnaSite Public API",
        default_version='v1',
        description=(
            "Public endpoints ArnaSite.\n\n"
            "- `POST /tenants/register/` — Daftarkan tenant baru. "
            "Butuh Bearer JWT dari Arna SSO dengan `is_owner=true`.\n"
            "- `GET /templates/` — Lihat daftar template (tanpa auth)."
        ),
    ),
    public=True,
    urlconf='config.public_urls',
    permission_classes=(permissions.AllowAny,),
    authentication_classes=(ArnaJWTAuthentication,),
)

urlpatterns = [
    path("tenants/register/", include("core.register_urls")),
    path("templates/", include("core.urls")),
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-public-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-public-swagger-ui'),
]
