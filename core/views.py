import jwt
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, AuthenticationFailed
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from authentication.permissions import IsTenantMember, IsTenantAdmin, IsTenantOwner
from core.models import Template, TemplatePage, TemplateSection, TemplateBlock, TemplateListItem, Tenant, Domain
from core.serializers import (
    TemplateSerializer,
    TemplateWriteSerializer,
    TenantRegistrationSerializer,
    TenantSerializer,
    TenantUpdateSerializer,
    DomainSerializer,
)
from core.services import apply_template


class TemplateListView(ListAPIView):
    """
    Menampilkan semua template master yang aktif beserta struktur lengkapnya
    (sections → blocks → list items). Tidak memerlukan autentikasi.
    """
    queryset = Template.objects.filter(is_active=True).prefetch_related(
        "sections__blocks__list_items"
    )
    serializer_class = TemplateSerializer
    permission_classes = [AllowAny]


class TemplateDetailView(RetrieveAPIView):
    """
    Menampilkan detail satu template master beserta struktur lengkapnya
    (sections → blocks → list items). Tidak memerlukan autentikasi.
    """
    queryset = Template.objects.filter(is_active=True).prefetch_related(
        "sections__blocks__list_items"
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

    Jika tenant sudah memiliki konten, request akan ditolak dengan 409 kecuali
    `overwrite: true` dikirimkan — dalam hal itu seluruh konten lama akan dihapus.

    **Permission:** `site_admin` role atau `is_owner = true`.
    """
    def get_permissions(self):
        return [IsAuthenticated(), IsTenantMember(), IsTenantAdmin() | IsTenantOwner()]

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
                    'domain': 'toko-budi.arnasite.id',
                },
                'next_steps': [
                    'Access your site at: toko-budi.arnasite.id/swagger/',
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
    409: openapi.Response(
        description='Organisasi ini sudah memiliki tenant terdaftar.',
        examples={'application/json': {'error': 'A tenant for this organization already exists.'}},
    ),
}


class TenantRegisterView(APIView):
    """
    Mendaftarkan tenant baru di ArnaSite untuk sebuah organisasi Arna SSO.

    Endpoint ini dipanggil **sekali** saat org owner pertama kali setup sitenya.
    `org_id` diambil langsung dari JWT — tidak bisa dimanipulasi dari request body.

    Pada sukses:
    - Schema PostgreSQL baru dibuat otomatis (`auto_create_schema=True`).
    - Semua migrasi tenant dijalankan otomatis.
    - Domain didaftarkan dan langsung bisa diakses.

    **Permission:** Hanya `is_owner=true` dalam JWT.
    """
    permission_classes = [AllowAny]

    def _decode_jwt(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            raise AuthenticationFailed("Bearer token required.")

        token = auth_header.split(" ", 1)[1]

        from authentication.jwt_backends import get_cached_public_key
        public_key = get_cached_public_key(settings.SSO_JWT_PUBLIC_KEY_PATH)
        if not public_key:
            raise AuthenticationFailed("JWT verification unavailable. Check SSO_JWT_PUBLIC_KEY_PATH.")

        try:
            claims = jwt.decode(
                token,
                public_key,
                algorithms=[settings.SSO_JWT_ALGORITHM],
                options={
                    "require": ["exp", "user_id"],
                    "verify_aud": False,
                },
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

        if Tenant.objects.filter(sso_organization_id=org_id).exists():
            return Response(
                {"error": "A tenant for this organization already exists."},
                status=409,
            )

        serializer = TenantRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        slug        = data["slug"]
        schema_name = slug.replace("-", "_")

        try:
            tenant = Tenant.objects.create(
                schema_name=schema_name,
                name=data["name"],
                slug=slug,
                sso_organization_id=org_id,
            )
        except Exception as e:
            return Response({"error": f"Failed to create tenant: {str(e)}"}, status=400)

        try:
            Domain.objects.create(
                domain=data["domain"],
                tenant=tenant,
                is_primary=True,
            )
        except Exception as e:
            tenant.delete()
            return Response({"error": f"Failed to register domain: {str(e)}"}, status=400)

        return Response({
            "tenant": {
                "name": tenant.name,
                "slug": tenant.slug,
                "schema_name": tenant.schema_name,
                "domain": data["domain"],
            },
            "next_steps": [
                f"Access your site at: {data['domain']}/swagger/",
                "Apply a template: POST /api/tenants/current/apply-template/",
            ],
        }, status=201)


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
            return [IsAuthenticated(), IsTenantMember(), IsTenantAdmin() | IsTenantOwner()]
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


# ─── Domain Management ────────────────────────────────────────────────────────

_domain_list_response = openapi.Response(
    'Daftar domain tenant.',
    examples={
        'application/json': [
            {'id': 1, 'domain': 'yapu.arnatech.id', 'is_primary': True},
            {'id': 2, 'domain': 'yapu.localhost',   'is_primary': False},
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
            return [IsAuthenticated(), IsTenantMember(), IsTenantAdmin() | IsTenantOwner()]
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
        serializer = DomainSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        domain = serializer.save(tenant=tenant, is_primary=False)
        return Response(DomainSerializer(domain).data, status=201)


class DomainDetailView(APIView):
    """
    Hapus sebuah domain dari tenant ini.

    Domain **primary tidak bisa dihapus** — harus ada minimal satu domain aktif.
    Untuk mengganti domain primary, tambah domain baru lalu hubungi support.

    **Permission:** `site_admin` atau owner.
    """
    def get_permissions(self):
        return [IsAuthenticated(), IsTenantMember(), IsTenantAdmin() | IsTenantOwner()]

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
        domain.delete()
        return Response(status=204)


# ─── Tenant Template Management ───────────────────────────────────────────────

def _current_schema():
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
            return [IsAuthenticated(), IsTenantMember(), IsTenantAdmin() | IsTenantOwner()]
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
                # published for all OR owned by this tenant
                **{}
            )
            from django.db.models import Q
            qs = Template.objects.filter(is_active=True).filter(
                Q(is_published=True) | Q(source_tenant_schema=schema)
            )

        qs = qs.prefetch_related('pages__sections__blocks__list_items')
        return Response(TemplateSerializer(qs, many=True).data)

    @swagger_auto_schema(
        operation_summary='Buat template baru (private)',
        request_body=TemplateWriteSerializer,
        responses=_template_write_responses,
        security=[{'Bearer': []}],
    )
    def post(self, request):
        schema = _current_schema()
        serializer = TemplateWriteSerializer(data=request.data)
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
            return [IsAuthenticated(), IsTenantMember(), IsTenantAdmin() | IsTenantOwner()]
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
        return [IsAuthenticated(), IsTenantMember(), IsTenantAdmin() | IsTenantOwner()]

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
