from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from authentication.permissions import IsTenantMember
from sites.models import Section, ContentBlock, ListItem
from sites.serializers import (
    SectionSerializer, 
    ContentBlockSerializer, 
    ListItemSerializer
)

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
