from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction
from authentication.permissions import IsTenantMember, IsTenantAdmin, IsTenantOwner
from authentication.jwt_backends import ArnaJWTAuthentication
from sites.models import Section, ContentBlock, ListItem
from sites.serializers import SectionSerializer, ContentBlockSerializer, ListItemSerializer
from storage.views import MediaReferenceViewSet
from core.views import ApplyTemplateView

# --- Permission Policy ---
# IsAuthenticated: Ensures a valid user is present.
# IsTenantMember: Ensures the user belongs to the tenant they are trying to access.
# (IsTenantAdmin | IsTenantOwner): Ensures the user is either a 'site_admin' or the tenant owner.
ADMIN_PERMISSIONS = [IsAuthenticated, IsTenantMember, (IsTenantAdmin | IsTenantOwner)]
ADMIN_AUTHENTICATION = [ArnaJWTAuthentication]

# --- ViewSets for Admin API ---

class AdminSectionViewSet(viewsets.ModelViewSet):
    serializer_class = SectionSerializer
    authentication_classes = ADMIN_AUTHENTICATION
    permission_classes = ADMIN_PERMISSIONS

    def get_queryset(self):
        return Section.objects.all()

class AdminContentBlockViewSet(viewsets.ModelViewSet):
    serializer_class = ContentBlockSerializer
    authentication_classes = ADMIN_AUTHENTICATION
    permission_classes = ADMIN_PERMISSIONS
    queryset = ContentBlock.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        section_id = self.request.query_params.get("section")
        if section_id:
            queryset = queryset.filter(section_id=section_id)
        return queryset

class AdminListItemViewSet(viewsets.ModelViewSet):
    serializer_class = ListItemSerializer
    authentication_classes = ADMIN_AUTHENTICATION
    permission_classes = ADMIN_PERMISSIONS
    queryset = ListItem.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        block_id = self.request.query_params.get("block")
        if block_id:
            queryset = queryset.filter(block_id=block_id)
        return queryset

class AdminSectionReorderView(APIView):
    authentication_classes = ADMIN_AUTHENTICATION
    permission_classes = ADMIN_PERMISSIONS

    def patch(self, request):
        sections_data = request.data
        if not isinstance(sections_data, list):
            return Response({"error": "Expected a list of objects"}, status=400)
            
        import uuid
        with transaction.atomic():
            for item in sections_data:
                section_id = item.get("id")
                order = item.get("order")
                if section_id and order is not None:
                    try:
                        uuid.UUID(str(section_id))
                    except ValueError:
                        return Response({"error": f"Invalid UUID: {section_id}"}, status=400)
                    Section.objects.filter(id=section_id).update(order=order)
                    
        return Response({"status": "Reordered successfully"}, status=200)

class AdminMediaReferenceViewSet(MediaReferenceViewSet):
    """
    Inherits from the standard MediaReferenceViewSet but applies the stricter
    admin permission policy.
    """
    authentication_classes = ADMIN_AUTHENTICATION
    permission_classes = ADMIN_PERMISSIONS

class AdminApplyTemplateView(ApplyTemplateView):
    """
    Inherits from the standard ApplyTemplateView but applies the stricter
    admin permission policy.
    """
    authentication_classes = ADMIN_AUTHENTICATION
    permission_classes = ADMIN_PERMISSIONS
