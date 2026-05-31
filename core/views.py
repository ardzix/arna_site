"""Module for core.views."""
import jwt

import uuid
import logging
import requests as http
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.core.cache import cache
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, AuthenticationFailed
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from authentication.permissions import IsTenantMember, IsTenantAdmin, IsTenantOwner
from authentication.jwt_backends import _jwt_decode_kwargs, get_cached_public_key
from core.models import Template, TemplatePage, TemplateSection, TemplateBlock, TemplateListItem, Tenant, Domain
from core.serializers import (
    TemplateSerializer,
    TemplateWriteSerializer,
    TemplateManualCreateSerializer,
    TenantRegistrationSerializer,
    TenantSerializer,
    TenantUpdateSerializer,
    DomainSerializer,
    PremiumCheckoutSerializer,
)
from core.services import apply_template
from core.commerce import (
    CommerceClient,
    CommerceClientError,
    resolve_catalog_ids,
    bootstrap_free_plan_for_org,
)
from core.limits import (
    fetch_runtime_entitlements,
    assert_max_websites,
    assert_max_templates,
    assert_custom_domain_enabled,
    assert_template_manual_creation_enabled,
    LimitError,
)

logger = logging.getLogger(__name__)


class TemplateListView(ListAPIView):
    """
    Menampilkan semua template master yang aktif beserta struktur lengkapnya
    (sections → blocks → list items). Tidak memerlukan autentikasi.
    """
    queryset = Template.objects.filter(
        is_active=True,
        is_published=True,
    ).prefetch_related(
        "pages__sections__blocks__list_items",
        "sections__blocks__list_items",
    )
    serializer_class = TemplateSerializer
    permission_classes = [AllowAny]


class TemplateDetailView(RetrieveAPIView):
    """
    Menampilkan detail satu template master beserta struktur lengkapnya
    (sections → blocks → list items). Tidak memerlukan autentikasi.
    """
    queryset = Template.objects.filter(
        is_active=True,
        is_published=True,
    ).prefetch_related(
        "pages__sections__blocks__list_items",
        "sections__blocks__list_items",
    )
    serializer_class = TemplateSerializer
    permission_classes = [AllowAny]


_apply_template_body = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=['template_id'],
    properties={
        'template_id': openapi.Schema(
            type=openapi.TYPE_STRING,
            format='uuid',
            description='UUID template master yang ingin diterapkan.',
        ),
        'overwrite': openapi.Schema(
            type=openapi.TYPE_BOOLEAN,
            default=False,
            description=(
                'Jika `true`, seluruh konten tenant yang ada akan dihapus '
                'dan diganti dengan template ini.'
            ),
        ),
    },
)

_apply_template_responses = {
    200: openapi.Response(
        description='Template berhasil diterapkan.',
        examples={'application/json': {'status': 'template applied successfully'}},
    ),
    400: openapi.Response(description='Request tidak valid.'),
    401: openapi.Response(description='Token JWT tidak ada atau tidak valid.'),
    403: openapi.Response(description='User bukan member tenant ini atau tidak punya role admin/owner.'),
    404: openapi.Response(description='Template dengan ID tersebut tidak ditemukan.'),
    409: openapi.Response(
        description='Template sudah pernah diterapkan. Kirim `overwrite: true` untuk menimpa.',
        examples={'application/json': {'error': 'Template already applied. Pass overwrite=true to replace.'}},
    ),
}


class ApplyTemplateView(APIView):
    """
    Menerapkan template master ke tenant yang sedang aktif.

    Proses ini akan meng-clone seluruh struktur template (sections → blocks → list items)
    ke dalam schema PostgreSQL tenant. Semua konten dilakukan dalam satu transaksi atomik.
    Sistem menyimpan `source_template_id` pada setiap page hasil clone agar public API
    bisa mengembalikan root `template_id` secara langsung.

    Jika tenant sudah memiliki konten, request akan ditolak dengan 409 kecuali
    `overwrite: true` dikirimkan — dalam hal itu seluruh konten lama akan dihapus.

    **Permission:** `site_admin` role atau `is_owner = true`.
    """
    def get_permissions(self):
        return [IsAuthenticated(), IsTenantMember(), (IsTenantAdmin | IsTenantOwner)()]

    @swagger_auto_schema(
        operation_summary='Terapkan template ke tenant',
        request_body=_apply_template_body,
        responses=_apply_template_responses,
        security=[{'Bearer': []}],
    )
    def post(self, request):
        template_id = request.data.get("template_id")
        overwrite = str(request.data.get("overwrite", "false")).lower() == "true"

        if not template_id:
            return Response({"error": "template_id is required."}, status=400)

        from django.db import connection
        tenant = connection.tenant

        try:
            apply_template(tenant.schema_name, template_id, overwrite=overwrite)
        except Template.DoesNotExist:
            raise NotFound(detail=f"Template '{template_id}' not found.")
        except ValueError as e:
            return Response({"error": str(e)}, status=409)
        except Exception as e:
            return Response({"error": str(e)}, status=400)

        return Response({"status": "template applied successfully"}, status=200)


_register_responses = {
    201: openapi.Response(
        description='Tenant berhasil didaftarkan. Schema PostgreSQL dan domain telah dibuat.',
        examples={
            'application/json': {
                'tenant': {
                    'name': 'Toko Budi',
                    'slug': 'toko-budi',
                    'schema_name': 'toko_budi',
                    'domain': 'toko-budi.site.arnatech.id',
                    'frontend_default_domain': 'toko-budi.bisnisnaikkelas.com',
                },
                'next_steps': [
                    'Access your site at: toko-budi.site.arnatech.id/swagger/',
                    'Apply a template: POST /api/tenants/current/apply-template/',
                ],
            }
        },
    ),
    400: openapi.Response(description='Input tidak valid atau gagal membuat tenant/domain.'),
    401: openapi.Response(description='Token JWT tidak ada, tidak valid, atau sudah expired.'),
    403: openapi.Response(
        description='Hanya org owner (`is_owner=true` dalam JWT) yang boleh mendaftarkan tenant.',
    ),
    409: openapi.Response(description='Tenant/domain conflict (slug/domain sudah dipakai).'),
}


class TenantRegisterView(APIView):
    """
    Mendaftarkan tenant baru di ArnaSite untuk sebuah organisasi Arna SSO.

    Endpoint ini dapat dipanggil berkali-kali untuk membuat beberapa tenant
    di organisasi yang sama.
    `org_id` diambil langsung dari JWT — tidak bisa dimanipulasi dari request body.

    Pada sukses:
    - Schema PostgreSQL baru dibuat otomatis (`auto_create_schema=True`).
    - Semua migrasi tenant dijalankan otomatis.
    - Backend domain dan frontend domain digenerate otomatis dari slug.

    **Permission:** Hanya `is_owner=true` dalam JWT.
    """
    permission_classes = [AllowAny]
    DEFAULT_OWNER_PERMISSION = "arnasite.cms.manage"
    DEFAULT_OWNER_ROLE = "site_admin"
    SHARED_POOL_SCHEMA = "pool_shared"
    SHARED_POOL_KEY = "pool_shared"

    def _domain_suffixes(self):
        backend_suffix = str(getattr(settings, "BACKEND_DEFAULT_DOMAIN_SUFFIX", "site.arnatech.id")).strip(".")
        frontend_suffix = str(getattr(settings, "FRONTEND_DEFAULT_DOMAIN_SUFFIX", "bisnisnaikkelas.com")).strip(".")
        return backend_suffix, frontend_suffix

    def _bearer_token(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return ""
        return auth_header.split(" ", 1)[1]

    def _sso_headers(self, request):
        return {
            "Authorization": request.META.get("HTTP_AUTHORIZATION", ""),
            "Content-Type": "application/json",
        }

    def _sso_base_url(self):
        return settings.ARNA_SSO_BASE_URL.rstrip("/")

    def _extract_items(self, payload):
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            results = payload.get("results")
            if isinstance(results, list):
                return results
            data = payload.get("data")
            if isinstance(data, list):
                return data
        return []

    def _find_by_name(self, items, name):
        """Return the first object whose ``name`` matches the requested value."""
        for item in items:
            if item.get("name") == name:
                return item
        return None

    def _find_permission_for_org(self, permissions, permission_name, organization_id):
        """Return the permission matching both name and organization id."""
        for permission in permissions:
            if permission.get("name") != permission_name:
                continue
            if str(permission.get("organization")) == str(organization_id):
                return permission
        return None

    def _find_role_for_org(self, roles, role_name, organization_id):
        """Return the role matching both name and organization id."""
        for role in roles:
            if role.get("name") != role_name:
                continue
            if str(role.get("organization")) == str(organization_id):
                return role
        return None

    def _request_error_details(self, error):
        """Extract concise HTTP error details from a requests exception."""
        response = getattr(error, "response", None)
        if response is None:
            return {"status_code": None, "body": str(error)}
        try:
            body = response.json()
        except ValueError:
            body = (response.text or "").strip()
        if isinstance(body, str) and len(body) > 800:
            body = f"{body[:800]}...<truncated>"
        return {
            "status_code": response.status_code,
            "body": body,
        }

    def _member_id_for_user(self, members, user_id):
        if not user_id:
            return None
        for member in members:
            raw_user = member.get("user")
            if isinstance(raw_user, dict):
                raw_user = raw_user.get("id")
            if str(raw_user) == str(user_id):
                return member.get("id")
        return None

    def _role_already_assigned(self, user_roles, member_id, role_id):
        for user_role in user_roles:
            org_member = user_role.get("organization_member")
            if isinstance(org_member, dict):
                org_member = org_member.get("id")
            role = user_role.get("role")
            if isinstance(role, dict):
                role = role.get("id")
            if str(org_member) == str(member_id) and str(role) == str(role_id):
                return True
        return False

    def _provision_sso_iam(self, request, claims):
        """
        Best-effort provisioning of default IAM objects in SSO for new org:
        - set current organization session
        - ensure default permission exists
        - ensure site_admin role exists with that permission
        - assign role to current user (org owner)
        """
        if not getattr(settings, "SSO_IAM_PROVISION_ON_REGISTER", True):
            return {
                "ok": True,
                "skipped": True,
                "message": "SSO IAM provisioning is disabled by SSO_IAM_PROVISION_ON_REGISTER.",
            }

        org_id = claims.get("org_id")
        user_id = claims.get("user_id")
        if not org_id or not user_id:
            return {
                "ok": False,
                "message": "Skipped IAM provisioning: token missing org_id or user_id.",
            }

        base = self._sso_base_url()
        headers = self._sso_headers(request)

        try:
            # 1) Set active org context in SSO
            current_resp = http.post(
                f"{base}/organizations/current/",
                json={"organization_id": org_id},
                headers=headers,
                timeout=10,
            )
            current_resp.raise_for_status()

            # 2) Ensure permission exists
            perm_list_resp = http.get(
                f"{base}/iam/permissions/",
                headers=headers,
                timeout=10,
            )
            perm_list_resp.raise_for_status()
            permissions = self._extract_items(perm_list_resp.json())
            permission = self._find_permission_for_org(
                permissions,
                self.DEFAULT_OWNER_PERMISSION,
                org_id,
            )
            if not permission:
                perm_create_resp = http.post(
                    f"{base}/iam/permissions/",
                    json={
                        "name": self.DEFAULT_OWNER_PERMISSION,
                        "description": "Manage ArnaSite CMS content and tenant configuration.",
                    },
                    headers=headers,
                    timeout=10,
                )
                perm_create_resp.raise_for_status()
                permission = perm_create_resp.json()
            permission_id = permission.get("id")
            if not permission_id:
                raise ValueError("SSO permission response missing id.")

            # 3) Ensure role exists
            role_list_resp = http.get(
                f"{base}/iam/roles/",
                headers=headers,
                timeout=10,
            )
            role_list_resp.raise_for_status()
            roles = self._extract_items(role_list_resp.json())
            role = self._find_role_for_org(
                roles,
                self.DEFAULT_OWNER_ROLE,
                org_id,
            )
            if not role:
                role_create_resp = http.post(
                    f"{base}/iam/roles/",
                    json={
                        "name": self.DEFAULT_OWNER_ROLE,
                        "description": "Default CMS admin role for ArnaSite tenant.",
                        "permission_ids": [permission_id],
                    },
                    headers=headers,
                    timeout=10,
                )
                role_create_resp.raise_for_status()
                role = role_create_resp.json()
            role_id = role.get("id")
            if not role_id:
                raise ValueError("SSO role response missing id.")

            # 4) Resolve organization member id for owner user
            member_list_resp = http.get(
                f"{base}/organizations/{org_id}/members/",
                headers=headers,
                timeout=10,
            )
            member_list_resp.raise_for_status()
            members = self._extract_items(member_list_resp.json())
            member_id = self._member_id_for_user(members, user_id)
            if not member_id:
                raise ValueError("Cannot map current user to organization member in SSO.")

            # 5) Assign role if not already assigned
            user_role_list_resp = http.get(
                f"{base}/iam/user-roles/",
                headers=headers,
                timeout=10,
            )
            user_role_list_resp.raise_for_status()
            user_roles = self._extract_items(user_role_list_resp.json())

            if not self._role_already_assigned(user_roles, member_id, role_id):
                assign_resp = http.post(
                    f"{base}/iam/user-roles/",
                    json={
                        "organization_member": member_id,
                        "role": role_id,
                    },
                    headers=headers,
                    timeout=10,
                )
                assign_resp.raise_for_status()

            return {
                "ok": True,
                "permission": self.DEFAULT_OWNER_PERMISSION,
                "role": self.DEFAULT_OWNER_ROLE,
                "organization_id": str(org_id),
                "user_id": str(user_id),
            }
        except (http.RequestException, ValueError) as e:
            error_details = self._request_error_details(e)
            logger.warning(
                "SSO IAM provisioning failed for org_id=%s: %s; details=%s",
                org_id,
                e,
                error_details,
            )
            return {
                "ok": False,
                "message": f"Tenant created, but SSO IAM provisioning failed: {e}",
                "organization_id": str(org_id),
                "sso_error": error_details,
            }

    def _decode_jwt(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            raise AuthenticationFailed("Bearer token required.")

        token = auth_header.split(" ", 1)[1]

        public_key = get_cached_public_key(settings.SSO_JWT_PUBLIC_KEY_PATH)
        if not public_key:
            raise AuthenticationFailed("JWT verification unavailable. Check SSO_JWT_PUBLIC_KEY_PATH.")

        try:
            claims = jwt.decode(
                token,
                public_key,
                **_jwt_decode_kwargs(),
            )
        except jwt.PyJWTError as e:
            raise AuthenticationFailed(f"Invalid or expired JWT token: {e}")

        return claims

    @swagger_auto_schema(
        operation_summary='Daftarkan tenant baru',
        request_body=TenantRegistrationSerializer,
        responses=_register_responses,
        security=[{'Bearer': []}],
    )
    def post(self, request):
        try:
            claims = self._decode_jwt(request)
        except AuthenticationFailed as e:
            return Response({"error": str(e.detail)}, status=401)

        org_id = claims.get("org_id")
        if not org_id:
            return Response(
                {"error": "Token tidak menyertakan org_id. Pastikan akun kamu sudah tergabung dalam sebuah organisasi di Arna SSO."},
                status=403,
            )

        if not claims.get("is_owner"):
            return Response(
                {"error": "Hanya owner organisasi yang bisa mendaftarkan tenant. Pastikan kamu login sebagai owner di Arna SSO (is_owner=true)."},
                status=403,
            )

        serializer = TenantRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        slug        = data["slug"]
        schema_name = self.SHARED_POOL_SCHEMA
        tenancy_mode = Tenant.TENANCY_SHARED
        shared_pool_key = self.SHARED_POOL_KEY

        # Package/limit source of truth is Commerce.
        # Enforce max_websites before tenant creation.
        try:
            entitlements = fetch_runtime_entitlements(str(org_id), self._bearer_token(request))
            current_count = Tenant.objects.filter(sso_organization_id=org_id, is_active=True).count()
            assert_max_websites(entitlements, current_count)
        except CommerceClientError:
            # Fallback: if runtime entitlements are unavailable, allow registration
            # and rely on subsequent entitlement sync/retry.
            pass
        except LimitError as e:
            return Response({"error": str(e)}, status=403)

        backend_suffix, frontend_suffix = self._domain_suffixes()
        backend_domain_value = f"{slug}.{backend_suffix}" if backend_suffix else slug
        frontend_default = f"{slug}.{frontend_suffix}" if frontend_suffix else ""
        if Domain.objects.filter(domain=backend_domain_value).exists():
            return Response({"error": "Autogenerated backend domain already exists. Please use a different slug."}, status=409)
        if frontend_default and Domain.objects.filter(domain=frontend_default).exists():
            return Response({"error": "Autogenerated frontend domain already exists. Please use a different slug."}, status=409)

        try:
            tenant = Tenant(
                schema_name=schema_name,
                name=data["name"],
                slug=slug,
                sso_organization_id=org_id,
                plan=Tenant.PLAN_FREE,
                tenancy_mode=tenancy_mode,
                shared_pool_key=shared_pool_key,
            )
            # Shared tenants reuse one pool schema. Create schema only once.
            if tenancy_mode == Tenant.TENANCY_SHARED and Tenant.objects.filter(schema_name=schema_name).exists():
                tenant.auto_create_schema = False
            else:
                tenant.auto_create_schema = True
            tenant.save()
        except Exception as e:
            return Response({"error": f"Failed to create tenant: {str(e)}"}, status=400)

        try:
            backend_domain = Domain.objects.create(
                domain=backend_domain_value,
                tenant=tenant,
                is_primary=True,
                role=Domain.ROLE_BACKEND_PRIMARY,
                status=Domain.STATUS_ACTIVE,
                is_primary_frontend=False,
                target_backend_domain=backend_domain_value,
                verified_at=timezone.now(),
            )
            if frontend_default:
                Domain.objects.create(
                    domain=frontend_default,
                    tenant=tenant,
                    is_primary=False,
                    role=Domain.ROLE_FRONTEND_DEFAULT,
                    status=Domain.STATUS_ACTIVE,
                    is_primary_frontend=True,
                    target_backend_domain=backend_domain.domain,
                    verified_at=timezone.now(),
                )
        except Exception as e:
            tenant.delete()
            return Response({"error": f"Failed to register domain: {str(e)}"}, status=400)

        commerce_bootstrap = {"ok": True, "skipped": True}
        if getattr(settings, "ARNA_COMMERCE_BOOTSTRAP_FREE_ON_REGISTER", True):
            try:
                commerce_bootstrap = {
                    "ok": True,
                    "result": bootstrap_free_plan_for_org(
                        organization_id=str(org_id),
                        bearer_token=self._bearer_token(request),
                    ),
                }
            except Exception as exc:
                logger.warning("Commerce free bootstrap failed for org_id=%s: %s", org_id, exc)
                commerce_bootstrap = {
                    "ok": False,
                    "error": f"Tenant created, but free package bootstrap failed: {exc}",
                }

        sso_sync = self._provision_sso_iam(request, claims)

        return Response({
            "tenant": {
                "name": tenant.name,
                "slug": tenant.slug,
                "schema_name": tenant.schema_name,
                "domain": backend_domain_value,
                "frontend_default_domain": frontend_default,
                "plan": tenant.plan,
                "tenancy_mode": tenant.tenancy_mode,
                "shared_pool_key": tenant.shared_pool_key,
            },
            "sso_sync": sso_sync,
            "commerce_bootstrap": commerce_bootstrap,
            "next_steps": [
                f"Access your site at: {backend_domain_value}/swagger/",
                "Apply a template: POST /api/tenants/current/apply-template/",
            ],
        }, status=201)


class TenantMyListView(APIView):
    """
    List tenant(s) for currently logged-in user org context (JWT org_id).
    """
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary='List tenant(s) for logged-in user',
        operation_description=(
            "Return tenant records linked to current JWT `org_id`.\n\n"
            "Useful on root/public domain (`site.arnatech.id`) to discover tenant domain(s).\n\n"
            "Next step:\n"
            "- Use returned primary domain to access tenant API, e.g. "
            "`https://{tenant_domain}/swagger/`."
        ),
        responses={
            200: openapi.Response(
                description='Tenant list for current JWT org context.',
                examples={
                    'application/json': {
                        'count': 1,
                        'results': [
                            {
                                'id': 'uuid',
                                'name': 'Nusa Prima',
                                'slug': 'nusa-prima',
                                'schema_name': 'nusa_prima',
                                'sso_organization_id': 'uuid',
                                'is_active': True,
                                'created_on': '2026-01-01T00:00:00Z',
                                'domains': [
                                    {'id': 1, 'domain': 'nusaprima.site.arnatech.id', 'is_primary': True}
                                ],
                            }
                        ],
                    }
                },
            ),
            401: openapi.Response(description='Missing/invalid/expired JWT token.'),
        },
        security=[{'Bearer': []}],
    )
    def get(self, request):
        org_id = str(getattr(request.user, 'org_id', '') or '')
        tenants = Tenant.objects.filter(
            sso_organization_id=org_id
        ).prefetch_related('domains').order_by('-created_on')
        payload = TenantSerializer(tenants, many=True).data
        return Response({'count': len(payload), 'results': payload}, status=200)


# ─── Tenant Self-Management (dari dalam tenant schema) ────────────────────────

_tenant_detail_responses = {
    200: openapi.Response('Detail tenant saat ini.', schema=TenantSerializer()),
    401: openapi.Response('Token JWT tidak valid.'),
    403: openapi.Response('Bukan member tenant ini.'),
}

_tenant_update_responses = {
    200: openapi.Response('Tenant berhasil diperbarui.', schema=TenantSerializer()),
    400: openapi.Response('Input tidak valid.'),
    403: openapi.Response('Hanya admin atau owner yang bisa mengubah data tenant.'),
}


class TenantDetailView(APIView):
    """
    Lihat atau ubah informasi tenant yang sedang aktif.

    - **GET**: Menampilkan detail tenant (nama, slug, schema, daftar domain).
      Bisa diakses semua member.
    - **PATCH**: Mengubah `name` tenant. Hanya `site_admin` atau owner.
    """
    def get_permissions(self):
        if self.request.method == 'PATCH':
            return [IsAuthenticated(), IsTenantMember(), (IsTenantAdmin | IsTenantOwner)()]
        return [IsAuthenticated(), IsTenantMember()]

    def _get_tenant(self):
        from django.db import connection
        return connection.tenant

    @swagger_auto_schema(
        operation_summary='Detail tenant saat ini',
        responses=_tenant_detail_responses,
        security=[{'Bearer': []}],
    )
    def get(self, request):
        tenant = self._get_tenant()
        return Response(TenantSerializer(tenant).data)

    @swagger_auto_schema(
        operation_summary='Update nama tenant',
        request_body=TenantUpdateSerializer,
        responses=_tenant_update_responses,
        security=[{'Bearer': []}],
    )
    def patch(self, request):
        tenant = self._get_tenant()
        serializer = TenantUpdateSerializer(tenant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TenantSerializer(tenant).data)


def _extract_bearer(request):
    """_extract_bearer helper."""
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Bearer "):
        return ""
    return auth_header.split(" ", 1)[1]


class TenantEntitlementRuntimeView(APIView):
    """
    Get runtime entitlement summary for current tenant organization from Arna Commerce.
    """
    def get_permissions(self):
        return [IsAuthenticated(), IsTenantMember()]

    @swagger_auto_schema(
        operation_summary='Get runtime entitlements (Commerce)',
        operation_description=(
            "Fetch runtime entitlement map from Arna Commerce for current organization.\n\n"
            "Next step:\n"
            "- Use returned `entitlements` map to enforce runtime limits in FE/BE flows."
        ),
        responses={
            200: openapi.Response(
                description='Runtime entitlement summary',
                examples={
                    'application/json': {
                        'organization_id': 'uuid',
                        'product_code': 'arna-site',
                        'entitlements': {
                            'arnasite.max_websites': '3',
                            'arnasite.max_templates': '20',
                        },
                    }
                },
            ),
            502: openapi.Response(description='Commerce request failed.'),
        },
        security=[{'Bearer': []}],
    )
    def get(self, request):
        org_id = str(getattr(request.user, "org_id", "") or "")
        token = _extract_bearer(request)
        product_code = getattr(settings, "ARNA_COMMERCE_PRODUCT_CODE", "arna-site")
        key_prefix = getattr(settings, "ARNA_COMMERCE_ENTITLEMENT_KEY_PREFIX", "arnasite.")

        cache_key = f"commerce:runtime-entitlements:{org_id}:{product_code}:{key_prefix}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached, status=200)

        try:
            payload = CommerceClient(token).runtime_entitlements(
                organization_id=org_id,
                product_code=product_code,
                key_prefix=key_prefix,
            )
        except CommerceClientError as exc:
            return Response({"error": str(exc)}, status=502)

        ttl = int(getattr(settings, "ARNA_COMMERCE_ENTITLEMENT_CACHE_TTL", 300))
        cache.set(cache_key, payload, timeout=ttl)
        return Response(payload, status=200)


class TenantPremiumCheckoutView(APIView):
    """
    Create premium checkout payment URL via Arna Commerce.
    """
    def get_permissions(self):
        return [IsAuthenticated(), IsTenantMember(), (IsTenantAdmin | IsTenantOwner)()]

    @swagger_auto_schema(
        operation_summary='Create premium checkout session',
        operation_description=(
            "Create order -> submit -> create payment (Xendit URL) for premium monthly plan.\n\n"
            "Next step:\n"
            "- Redirect user to returned payment URL from Commerce response."
        ),
        request_body=PremiumCheckoutSerializer,
        responses={
            200: openapi.Response(
                description='Premium checkout session created',
                examples={
                    'application/json': {
                        'order_id': 'uuid',
                        'submit': {'order': {'status': 'pending_payment'}},
                        'payment': {'invoice_url': 'https://checkout.xendit.co/...'},
                    }
                },
            ),
            502: openapi.Response(description='Commerce request failed.'),
        },
        security=[{'Bearer': []}],
    )
    def post(self, request):
        serializer = PremiumCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = _extract_bearer(request)
        org_id = str(getattr(request.user, "org_id", "") or "")
        product_code = getattr(settings, "ARNA_COMMERCE_PRODUCT_CODE", "arna-site")
        interval = serializer.validated_data.get("billing_interval", "monthly")
        if interval == "yearly":
            premium_plan_code = getattr(
                settings,
                "ARNA_COMMERCE_PREMIUM_ANNUAL_PLAN_CODE",
                "arna-site-premium-annually",
            )
        else:
            premium_plan_code = getattr(settings, "ARNA_COMMERCE_PREMIUM_PLAN_CODE", "arna-site-premium-monthly")
        payment_method = getattr(settings, "ARNA_COMMERCE_PREMIUM_PAYMENT_METHOD", "pg")

        client = CommerceClient(token)
        try:
            ids = resolve_catalog_ids(client, product_code, premium_plan_code)
            order = client.create_order(
                {
                    "organization_id": org_id,
                    "product": ids["product_id"],
                    "plan": ids["plan_id"],
                    "price": ids["price_id"],
                    "payment_method": payment_method,
                    "notes": "ArnaSite premium checkout",
                }
            )
            submit = client.submit_order(order["id"])
            payment = client.create_order_payment(order["id"], serializer.validated_data)
        except CommerceClientError as exc:
            return Response({"error": str(exc)}, status=502)

        return Response(
            {
                "order_id": order["id"],
                "submit": submit,
                "payment": payment,
            },
            status=200,
        )


# ─── Domain Management ────────────────────────────────────────────────────────

_domain_list_response = openapi.Response(
    'Daftar domain tenant.',
    examples={
        'application/json': [
            {'id': 1, 'domain': 'yapu.site.arnatech.id', 'is_primary': True, 'role': 'backend_primary', 'status': 'active'},
            {'id': 2, 'domain': 'yapu.bisnisnaikkelas.com', 'is_primary': False, 'is_primary_frontend': True, 'role': 'frontend_default', 'status': 'active'},
            {'id': 3, 'domain': 'yapu.com', 'is_primary': False, 'is_primary_frontend': False, 'role': 'frontend_custom', 'status': 'pending_verification'},
        ]
    },
)

_domain_add_body = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    required=['domain'],
    properties={
        'domain': openapi.Schema(
            type=openapi.TYPE_STRING,
            description='Domain atau subdomain baru, misal: `custom.domain.com`.',
        ),
        'role': openapi.Schema(
            type=openapi.TYPE_STRING,
            description='Optional. `frontend_custom` (default).',
        ),
        'is_primary_frontend': openapi.Schema(
            type=openapi.TYPE_BOOLEAN,
            description='Optional. Tandai sebagai domain frontend utama.',
        ),
    },
)

_domain_add_responses = {
    201: openapi.Response('Domain berhasil ditambahkan.', schema=DomainSerializer()),
    400: openapi.Response('Domain tidak valid atau sudah terdaftar.'),
    403: openapi.Response('Hanya admin atau owner.'),
}

_domain_delete_responses = {
    204: openapi.Response('Domain berhasil dihapus.'),
    400: openapi.Response('Domain primary tidak bisa dihapus.'),
    403: openapi.Response('Hanya admin atau owner.'),
    404: openapi.Response('Domain tidak ditemukan.'),
}


class DomainListCreateView(APIView):
    """
    List semua domain milik tenant ini, atau tambah domain baru.

    - **GET**: Semua member.
    - **POST**: Hanya `site_admin` atau owner. Domain yang ditambahkan otomatis
      `is_primary=false`. Primary domain hanya diset saat register awal.
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsTenantMember(), (IsTenantAdmin | IsTenantOwner)()]
        return [IsAuthenticated(), IsTenantMember()]

    def _get_tenant(self):
        from django.db import connection
        return connection.tenant

    @swagger_auto_schema(
        operation_summary='List domain tenant',
        responses={200: _domain_list_response},
        security=[{'Bearer': []}],
    )
    def get(self, request):
        tenant = self._get_tenant()
        domains = Domain.objects.filter(tenant=tenant)
        return Response(DomainSerializer(domains, many=True).data)

    @swagger_auto_schema(
        operation_summary='Tambah domain baru',
        request_body=_domain_add_body,
        responses=_domain_add_responses,
        security=[{'Bearer': []}],
    )
    def post(self, request):
        tenant = self._get_tenant()
        org_id = str(getattr(request.user, "org_id", "") or "")
        token = request.META.get("HTTP_AUTHORIZATION", "").split(" ", 1)[1] if request.META.get("HTTP_AUTHORIZATION", "").startswith("Bearer ") else ""
        try:
            entitlements = fetch_runtime_entitlements(org_id, token)
        except CommerceClientError as exc:
            return Response({"error": f"Failed reading package entitlements: {exc}"}, status=502)

        payload = dict(request.data)
        payload.setdefault("role", Domain.ROLE_FRONTEND_CUSTOM)
        payload.setdefault("status", Domain.STATUS_PENDING)
        payload.setdefault("is_primary_frontend", False)
        # User-created domains are always treated as custom frontend domains.
        # Backend/default frontend domains are system-generated during tenant registration.
        if payload.get("role") != Domain.ROLE_FRONTEND_CUSTOM:
            return Response(
                {"error": "Only custom frontend domains can be added manually."},
                status=400,
            )
        try:
            assert_custom_domain_enabled(entitlements)
        except LimitError as e:
            return Response({"error": str(e)}, status=403)

        serializer = DomainSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        backend_primary = Domain.objects.filter(
            tenant=tenant,
            role=Domain.ROLE_BACKEND_PRIMARY,
        ).first()
        verification_token = uuid.uuid4().hex
        verification_method = "txt"
        domain = serializer.save(
            tenant=tenant,
            is_primary=False,
            target_backend_domain=(backend_primary.domain if backend_primary else ""),
            verification_token=verification_token,
            verification_method=verification_method,
        )
        return Response(DomainSerializer(domain).data, status=201)


class DomainDetailView(APIView):
    """
    Hapus sebuah domain dari tenant ini.

    Domain **primary tidak bisa dihapus** — harus ada minimal satu domain aktif.
    Untuk mengganti domain primary, tambah domain baru lalu hubungi support.

    **Permission:** `site_admin` atau owner.
    """
    def get_permissions(self):
        return [IsAuthenticated(), IsTenantMember(), (IsTenantAdmin | IsTenantOwner)()]

    def _get_domain(self, pk):
        from django.db import connection
        tenant = connection.tenant
        return get_object_or_404(Domain, pk=pk, tenant=tenant)

    @swagger_auto_schema(
        operation_summary='Hapus domain tenant',
        responses=_domain_delete_responses,
        security=[{'Bearer': []}],
    )
    def delete(self, request, pk):
        domain = self._get_domain(pk)
        if domain.is_primary:
            return Response(
                {"error": "Domain primary tidak bisa dihapus. Tambah domain baru terlebih dahulu, lalu hubungi support untuk memindahkan primary."},
                status=400,
            )
        if domain.role == Domain.ROLE_FRONTEND_DEFAULT:
            return Response(
                {"error": "Frontend default domain tidak bisa dihapus."},
                status=400,
            )
        domain.delete()
        return Response(status=204)

    @swagger_auto_schema(
        operation_summary='Update domain flags (frontend primary)',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'is_primary_frontend': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'status': openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
        responses={200: openapi.Response('Domain updated.', schema=DomainSerializer())},
        security=[{'Bearer': []}],
    )
    def patch(self, request, pk):
        domain = self._get_domain(pk)
        if "is_primary_frontend" in request.data:
            make_primary = bool(request.data.get("is_primary_frontend"))
            if make_primary:
                Domain.objects.filter(
                    tenant=domain.tenant,
                    is_primary_frontend=True,
                ).update(is_primary_frontend=False)
                domain.is_primary_frontend = True
        if "status" in request.data and request.data.get("status") in {
            Domain.STATUS_ACTIVE,
            Domain.STATUS_PENDING,
            Domain.STATUS_FAILED,
        }:
            domain.status = request.data["status"]
            if domain.status == Domain.STATUS_ACTIVE:
                domain.verified_at = timezone.now()
        domain.save()
        return Response(DomainSerializer(domain).data, status=200)


class PublicDomainResolveView(APIView):
    """
    Resolve frontend/public host ke tenant + backend domain target.

    FE dapat memanggil endpoint ini untuk tahu request host tertentu harus
    consume public content dari backend domain tenant mana.
    """
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary='Resolve frontend host to backend domain mapping',
        manual_parameters=[
            openapi.Parameter(
                'host', openapi.IN_QUERY, description='Frontend/public host, e.g. bnk.bisnisnaikkelas.com',
                type=openapi.TYPE_STRING, required=True
            ),
        ],
        responses={
            200: openapi.Response(
                'Resolved.',
                examples={
                    'application/json': {
                        'host': 'bnk.bisnisnaikkelas.com',
                        'tenant': {'name': 'BNK', 'slug': 'bnk'},
                        'backend_domain': 'bnk.site.arnatech.id',
                        'public_api_base_url': 'https://bnk.site.arnatech.id/api/public',
                    }
                },
            ),
            404: openapi.Response('Domain not found.'),
        },
        security=[],
    )
    def get(self, request):
        host = (request.query_params.get("host") or "").strip().lower()
        if not host:
            return Response({"error": "host query param is required."}, status=400)

        with schema_context("public"):
            domain = Domain.objects.select_related("tenant").filter(domain=host).first()
            if not domain:
                return Response({"error": "Domain not found."}, status=404)

            backend = (
                domain.target_backend_domain
                or Domain.objects.filter(
                    tenant=domain.tenant,
                    role=Domain.ROLE_BACKEND_PRIMARY,
                ).values_list("domain", flat=True).first()
                or ""
            )
            scheme = "https"
            api_base = f"{scheme}://{backend}/api/public" if backend else ""
            return Response(
                {
                    "host": host,
                    "tenant": {"name": domain.tenant.name, "slug": domain.tenant.slug},
                    "backend_domain": backend,
                    "public_api_base_url": api_base,
                },
                status=200,
            )


# ─── Tenant Template Management ───────────────────────────────────────────────

def _current_schema():
    """_current_schema helper."""
    from django.db import connection
    return connection.tenant.schema_name


_template_browse_responses = {
    200: openapi.Response('Daftar template.', schema=TemplateSerializer(many=True)),
}

_template_write_responses = {
    201: openapi.Response('Template berhasil dibuat.', schema=TemplateSerializer()),
    400: openapi.Response('Input tidak valid.'),
    403: openapi.Response('Hanya admin/owner.'),
}

_publish_responses = {
    200: openapi.Response('Status publish berhasil diubah.',
         examples={'application/json': {'status': 'published', 'is_published': True}}),
    403: openapi.Response('Bukan pemilik template ini.'),
    404: openapi.Response('Template tidak ditemukan.'),
}


class TenantTemplateListCreateView(APIView):
    """
    Browse dan buat template dari dalam tenant.

    **GET — Browse template:**
    - `?visibility=public` → semua template yang sudah dipublish (katalog global)
    - `?visibility=private` → hanya template milik tenant ini (belum dipublish)
    - Tanpa filter → semua (public + milik tenant ini)

    **POST — Buat template baru (private):**
    Template baru selalu private (`is_published=False`) sampai secara eksplisit
    di-publish via `POST /api/templates/<id>/publish/`.

    **Permission GET:** semua member. **Permission POST:** admin/owner.
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsTenantMember(), (IsTenantAdmin | IsTenantOwner)()]
        return [IsAuthenticated(), IsTenantMember()]

    @swagger_auto_schema(
        operation_summary='Browse template',
        manual_parameters=[
            openapi.Parameter('visibility', openapi.IN_QUERY,
                type=openapi.TYPE_STRING, enum=['public', 'private'],
                description='`public` = katalog global. `private` = milik saya. Kosong = semua.'),
        ],
        responses=_template_browse_responses,
        security=[{'Bearer': []}],
    )
    def get(self, request):
        schema = _current_schema()
        visibility = request.query_params.get('visibility')

        if visibility == 'public':
            qs = Template.objects.filter(is_active=True, is_published=True)
        elif visibility == 'private':
            qs = Template.objects.filter(is_active=True, source_tenant_schema=schema,
                                         is_published=False)
        else:
            qs = Template.objects.filter(is_active=True).filter(
                Q(is_published=True) | Q(source_tenant_schema=schema)
            )

        qs = qs.prefetch_related('pages__sections__blocks__list_items')
        return Response(TemplateSerializer(qs, many=True).data)

    @swagger_auto_schema(
        operation_summary='Buat template baru (private)',
        request_body=TemplateManualCreateSerializer,
        responses=_template_write_responses,
        security=[{'Bearer': []}],
    )
    def post(self, request):
        schema = _current_schema()
        org_id = str(getattr(request.user, "org_id", "") or "")
        token = _extract_bearer(request)
        try:
            entitlements = fetch_runtime_entitlements(org_id, token)
            assert_template_manual_creation_enabled(entitlements)
            current_templates = Template.objects.filter(
                is_active=True,
                source_tenant_schema=schema,
            ).count()
            assert_max_templates(entitlements, current_templates)
        except CommerceClientError as exc:
            return Response({"error": f"Failed reading package entitlements: {exc}"}, status=502)
        except LimitError as e:
            return Response({"error": str(e)}, status=403)

        serializer = TemplateManualCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        template = serializer.save(
            is_published=False,
            source_tenant_schema=schema,
        )
        return Response(
            TemplateSerializer(template).data,
            status=201,
        )


class TenantTemplateDetailView(APIView):
    """
    Detail, update, atau hapus template milik tenant ini.

    Hanya template yang `source_tenant_schema` == schema tenant aktif
    yang bisa diubah/dihapus. Template sistem (null) tidak bisa diedit.

    **Permission:** semua member bisa GET. Admin/owner untuk PATCH/DELETE.
    """
    def get_permissions(self):
        if self.request.method in {'PATCH', 'DELETE'}:
            return [IsAuthenticated(), IsTenantMember(), (IsTenantAdmin | IsTenantOwner)()]
        return [IsAuthenticated(), IsTenantMember()]

    def _get_owned_template(self, pk):
        schema = _current_schema()
        return get_object_or_404(Template, pk=pk, source_tenant_schema=schema, is_active=True)

    @swagger_auto_schema(
        operation_summary='Detail template',
        responses={200: openapi.Response('', schema=TemplateSerializer())},
        security=[{'Bearer': []}],
    )
    def get(self, request, pk):
        schema = _current_schema()
        from django.db.models import Q
        template = get_object_or_404(
            Template.objects.prefetch_related('pages__sections__blocks__list_items'),
            Q(is_published=True) | Q(source_tenant_schema=schema),
            pk=pk, is_active=True,
        )
        return Response(TemplateSerializer(template).data)

    @swagger_auto_schema(
        operation_summary='Update template milik saya',
        request_body=TemplateWriteSerializer,
        responses={200: openapi.Response('', schema=TemplateSerializer())},
        security=[{'Bearer': []}],
    )
    def patch(self, request, pk):
        template = self._get_owned_template(pk)
        serializer = TemplateWriteSerializer(template, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TemplateSerializer(template).data)

    @swagger_auto_schema(
        operation_summary='Hapus template milik saya',
        responses={
            204: openapi.Response('Template berhasil dihapus.'),
            403: openapi.Response('Bukan pemilik template atau template sudah dipublish.'),
        },
        security=[{'Bearer': []}],
    )
    def delete(self, request, pk):
        template = self._get_owned_template(pk)
        if template.is_published:
            return Response(
                {"error": "Template yang sudah dipublish tidak bisa dihapus langsung. "
                           "Unpublish terlebih dahulu via DELETE /api/templates/<id>/publish/."},
                status=403,
            )
        template.delete()
        return Response(status=204)


class TenantTemplatePublishView(APIView):
    """
    Publish atau unpublish template milik tenant ini ke katalog global.

    - **POST** → publish (`is_published=True`): template muncul di `GET /templates/`.
    - **DELETE** → unpublish (`is_published=False`): template disembunyikan dari katalog.

    Hanya pemilik template (`source_tenant_schema` == schema aktif) yang bisa melakukan ini.

    **Permission:** admin/owner.
    """
    def get_permissions(self):
        return [IsAuthenticated(), IsTenantMember(), (IsTenantAdmin | IsTenantOwner)()]

    def _get_owned(self, pk):
        schema = _current_schema()
        return get_object_or_404(Template, pk=pk, source_tenant_schema=schema, is_active=True)

    @swagger_auto_schema(
        operation_summary='Publish template ke katalog global',
        responses=_publish_responses,
        request_body=openapi.Schema(type=openapi.TYPE_OBJECT),
        security=[{'Bearer': []}],
    )
    def post(self, request, pk):
        template = self._get_owned(pk)
        template.is_published = True
        template.save(update_fields=['is_published'])
        return Response({'status': 'published', 'is_published': True})

    @swagger_auto_schema(
        operation_summary='Unpublish template dari katalog global',
        responses=_publish_responses,
        security=[{'Bearer': []}],
    )
    def delete(self, request, pk):
        template = self._get_owned(pk)
        template.is_published = False
        template.save(update_fields=['is_published'])
        return Response({'status': 'unpublished', 'is_published': False})
