from rest_framework.views import APIView
from rest_framework.generics import (
    ListCreateAPIView, RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from authentication.permissions import IsTenantMember, IsTenantAdmin, IsTenantOwner
from sites.models import Page, Section, ContentBlock, ListItem
from sites.serializers import (
    PageSerializer, PageDetailSerializer,
    SectionSerializer, ContentBlockSerializer, ListItemSerializer,
)

WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def _read_perms():
    return [IsAuthenticated(), IsTenantMember()]


def _write_perms():
    return [IsAuthenticated(), IsTenantMember(), IsTenantAdmin() | IsTenantOwner()]


# ─── Public ───────────────────────────────────────────────────────────────────

class PublicSiteView(APIView):
    """
    Entry point frontend publik.

    - **GET /api/public/site/** — Daftar semua halaman aktif (tanpa konten section).
    - **GET /api/public/site/{slug}/** — Konten lengkap satu halaman beserta
      sections → blocks → items.

    Tidak memerlukan autentikasi.
    """
    permission_classes = [AllowAny]

    def get(self, request, slug=None):
        from django.db import connection
        tenant = connection.tenant

        if slug:
            page = get_object_or_404(
                Page.objects.prefetch_related("sections__blocks__items"),
                slug=slug, is_active=True,
            )
            return Response(PageDetailSerializer(page).data)

        pages = Page.objects.filter(is_active=True).order_by("order", "title")
        return Response({
            "tenant": {"name": tenant.name, "slug": tenant.slug},
            "pages":  PageSerializer(pages, many=True).data,
        })


# ─── Reorder helper ───────────────────────────────────────────────────────────

_reorder_body = openapi.Schema(
    type=openapi.TYPE_ARRAY,
    items=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['id', 'order'],
        properties={
            'id':    openapi.Schema(type=openapi.TYPE_STRING, format='uuid'),
            'order': openapi.Schema(type=openapi.TYPE_INTEGER),
        },
    ),
)


def _do_reorder(model, data):
    if not isinstance(data, list):
        return Response({"error": "Expected a list of {id, order}"}, status=400)
    with transaction.atomic():
        for item in data:
            if item.get("id") and item.get("order") is not None:
                model.objects.filter(id=item["id"]).update(order=item["order"])
    return Response({"status": "reordered"})


# ─── Pages ────────────────────────────────────────────────────────────────────

class PageListCreateView(ListCreateAPIView):
    """
    **GET** — Daftar semua halaman tenant.

    **POST** — Buat halaman baru. Slug di-generate otomatis dari title jika tidak diisi.
    Satu halaman bisa ditandai `is_home=true` sebagai homepage.

    Permission: GET → member. POST → admin/owner.
    """
    def get_permissions(self):
        if self.request.method == 'POST':
            return _write_perms()
        return _read_perms()

    def get_queryset(self):
        return Page.objects.all()

    def get_serializer_class(self):
        return PageSerializer


class PageDetailView(RetrieveUpdateDestroyAPIView):
    """
    **GET** — Detail page, termasuk list sections yang dimiliki.

    **PATCH** — Update metadata page (title, slug, is_home, is_active, order, meta).

    **DELETE** — Hapus halaman beserta seluruh sections, blocks, dan items di dalamnya.

    Permission: GET → member. PATCH/DELETE → admin/owner.
    """
    lookup_url_kwarg = 'page_id'

    def get_permissions(self):
        if self.request.method in WRITE_METHODS:
            return _write_perms()
        return _read_perms()

    def get_queryset(self):
        return Page.objects.prefetch_related("sections__blocks__items")

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return PageDetailSerializer
        return PageSerializer


class PageReorderView(APIView):
    """
    Ubah urutan beberapa halaman sekaligus.

    Kirim array `[{id, order}]`. Permission: admin/owner.
    """
    def get_permissions(self):
        return _write_perms()

    @swagger_auto_schema(request_body=_reorder_body,
                         operation_summary='Reorder pages',
                         security=[{'Bearer': []}])
    def patch(self, request):
        return _do_reorder(Page, request.data)


# ─── Sections (nested under Page) ─────────────────────────────────────────────

class SectionListCreateView(ListCreateAPIView):
    """
    **GET** `/api/pages/{page_id}/sections/` — Semua sections milik halaman ini.

    **POST** — Buat section baru di halaman ini.

    Permission: GET → member. POST → admin/owner.
    """
    serializer_class = SectionSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return _write_perms()
        return _read_perms()

    def get_queryset(self):
        get_object_or_404(Page, pk=self.kwargs['page_id'])
        return Section.objects.filter(page_id=self.kwargs['page_id'])

    def perform_create(self, serializer):
        page = get_object_or_404(Page, pk=self.kwargs['page_id'])
        serializer.save(page=page)


class SectionDetailView(RetrieveUpdateDestroyAPIView):
    """
    **GET/PATCH/DELETE** `/api/pages/{page_id}/sections/{section_id}/`

    Permission: GET → member. PATCH/DELETE → admin/owner.
    """
    serializer_class = SectionSerializer
    lookup_url_kwarg  = 'section_id'

    def get_permissions(self):
        if self.request.method in WRITE_METHODS:
            return _write_perms()
        return _read_perms()

    def get_queryset(self):
        return Section.objects.filter(page_id=self.kwargs['page_id'])


class SectionReorderView(APIView):
    """
    Ubah urutan sections dalam halaman ini. Permission: admin/owner.
    """
    def get_permissions(self):
        return _write_perms()

    @swagger_auto_schema(request_body=_reorder_body,
                         operation_summary='Reorder sections',
                         security=[{'Bearer': []}])
    def patch(self, request, page_id):
        return _do_reorder(Section, request.data)


# ─── Blocks (nested under Section) ────────────────────────────────────────────

class BlockListCreateView(ListCreateAPIView):
    """
    **GET** `/api/pages/{page_id}/sections/{section_id}/blocks/`

    **POST** — Buat block baru dalam section ini.

    Permission: GET → member. POST → admin/owner.
    """
    serializer_class = ContentBlockSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return _write_perms()
        return _read_perms()

    def get_queryset(self):
        get_object_or_404(Section, pk=self.kwargs['section_id'],
                          page_id=self.kwargs['page_id'])
        return ContentBlock.objects.filter(section_id=self.kwargs['section_id'])

    def perform_create(self, serializer):
        section = get_object_or_404(Section, pk=self.kwargs['section_id'],
                                    page_id=self.kwargs['page_id'])
        serializer.save(section=section)


class BlockDetailView(RetrieveUpdateDestroyAPIView):
    """
    **GET/PATCH/DELETE** `/api/pages/{page_id}/sections/{section_id}/blocks/{block_id}/`

    Permission: GET → member. PATCH/DELETE → admin/owner.
    """
    serializer_class  = ContentBlockSerializer
    lookup_url_kwarg  = 'block_id'

    def get_permissions(self):
        if self.request.method in WRITE_METHODS:
            return _write_perms()
        return _read_perms()

    def get_queryset(self):
        return ContentBlock.objects.filter(section_id=self.kwargs['section_id'])


# ─── Items (nested under Block) ───────────────────────────────────────────────

class ItemListCreateView(ListCreateAPIView):
    """
    **GET** `/api/pages/{page_id}/sections/{section_id}/blocks/{block_id}/items/`

    **POST** — Buat list item baru dalam block ini.

    Permission: GET → member. POST → admin/owner.
    """
    serializer_class = ListItemSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return _write_perms()
        return _read_perms()

    def get_queryset(self):
        get_object_or_404(ContentBlock, pk=self.kwargs['block_id'],
                          section_id=self.kwargs['section_id'])
        return ListItem.objects.filter(block_id=self.kwargs['block_id'])

    def perform_create(self, serializer):
        block = get_object_or_404(ContentBlock, pk=self.kwargs['block_id'],
                                  section_id=self.kwargs['section_id'])
        serializer.save(block=block)


class ItemDetailView(RetrieveUpdateDestroyAPIView):
    """
    **GET/PATCH/DELETE**
    `/api/pages/{page_id}/sections/{section_id}/blocks/{block_id}/items/{item_id}/`

    Permission: GET → member. PATCH/DELETE → admin/owner.
    """
    serializer_class = ListItemSerializer
    lookup_url_kwarg = 'item_id'

    def get_permissions(self):
        if self.request.method in WRITE_METHODS:
            return _write_perms()
        return _read_perms()

    def get_queryset(self):
        return ListItem.objects.filter(block_id=self.kwargs['block_id'])
