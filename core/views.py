from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from authentication.permissions import IsTenantMember

from core.models import Template
from core.serializers import TemplateSerializer
from core.services import apply_template


class TemplateListView(ListAPIView):
    """GET /templates/ — list all active templates (public schema, no auth required)"""
    queryset = Template.objects.filter(is_active=True).prefetch_related(
        "sections__blocks__list_items"
    )
    serializer_class = TemplateSerializer
    permission_classes = [AllowAny]


class TemplateDetailView(RetrieveAPIView):
    """GET /templates/{id}/ — single template with full nested structure"""
    queryset = Template.objects.filter(is_active=True).prefetch_related(
        "sections__blocks__list_items"
    )
    serializer_class = TemplateSerializer
    permission_classes = [AllowAny]


class ApplyTemplateView(APIView):
    """POST /tenants/current/apply-template"""
    permission_classes = [IsAuthenticated, IsTenantMember]

    def post(self, request):
        template_id = request.data.get("template_id")
        overwrite = str(request.data.get("overwrite", "false")).lower() == "true"

        if not template_id:
            return Response({"error": "template_id is required."}, status=400)

        from django.db import connection
        tenant = connection.tenant  # already set by TenantMainMiddleware

        try:
            success = apply_template(tenant.schema_name, template_id, overwrite=overwrite)
        except Template.DoesNotExist:
            raise NotFound(detail=f"Template '{template_id}' not found.")
        except ValueError as e:
            return Response({"error": str(e)}, status=409)
        except Exception as e:
            return Response({"error": str(e)}, status=400)

        return Response({"status": "template applied successfully"}, status=200)
