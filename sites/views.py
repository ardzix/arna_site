from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.generics import (
    RetrieveUpdateDestroyAPIView,
    ListCreateAPIView,
)
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from authentication.permissions import IsTenantMember
from sites.models import Section, ContentBlock, ListItem
from sites.serializers import (
    SectionSerializer,
    ContentBlockSerializer,
    ListItemSerializer,
)


class PublicSiteView(APIView):
    """
    GET /site/ — Returns all active sections + blocks for unauthenticated
    public rendering of a tenant's website. No auth required.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        sections = Section.objects.filter(is_active=True).prefetch_related(
            "blocks__items"
        )
        serializer = SectionSerializer(sections, many=True)
        return Response(serializer.data)


class SectionViewSet(viewsets.ModelViewSet):
    queryset = Section.objects.all()
    serializer_class = SectionSerializer
    permission_classes = [IsAuthenticated, IsTenantMember]


class ContentBlockViewSet(viewsets.ModelViewSet):
    serializer_class = ContentBlockSerializer
    permission_classes = [IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        queryset = ContentBlock.objects.all()
        section_id = self.request.query_params.get("section")
        if section_id:
            queryset = queryset.filter(section_id=section_id)
        return queryset


class ListItemViewSet(viewsets.ModelViewSet):
    serializer_class = ListItemSerializer
    permission_classes = [IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        queryset = ListItem.objects.all()
        block_id = self.request.query_params.get("block")
        if block_id:
            queryset = queryset.filter(block_id=block_id)
        return queryset


class BlockDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/sites/blocks/<pk>/
    Single block detail — alternative to the ViewSet route.
    """
    queryset = ContentBlock.objects.all()
    serializer_class = ContentBlockSerializer
    permission_classes = [IsAuthenticated, IsTenantMember]


class ItemListCreateView(ListCreateAPIView):
    """
    GET /api/sites/blocks/<block_id>/items/
    Lists all items nested under a given block, and allows creating new ones.
    """
    serializer_class = ListItemSerializer
    permission_classes = [IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        return ListItem.objects.filter(block_id=self.kwargs["block_id"])

    def perform_create(self, serializer):
        block = get_object_or_404(ContentBlock, pk=self.kwargs["block_id"])
        serializer.save(block=block)


class ItemDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/sites/items/<pk>/
    Single list item detail.
    """
    queryset = ListItem.objects.all()
    serializer_class = ListItemSerializer
    permission_classes = [IsAuthenticated, IsTenantMember]
