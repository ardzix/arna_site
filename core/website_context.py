"""Public routing metadata for registered website origins; never login authority."""

import re
from uuid import UUID, uuid4

from django_tenants.utils import schema_context
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Domain


def failure(code, detail, status):
    return Response({"error": code, "detail": detail, "request_id": str(uuid4())}, status=status,
                    headers={"Cache-Control": "no-store"})


class PublicWebsiteContextView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        host = request.query_params.get("host", "")
        if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}", host):
            return failure("invalid_host", "Use an exact website hostname.", 400)
        with schema_context("public"):
            domain = Domain.objects.select_related("tenant").filter(
                domain=host,
                role__in=[Domain.ROLE_FRONTEND_DEFAULT, Domain.ROLE_FRONTEND_CUSTOM],
                status=Domain.STATUS_ACTIVE,
                verified_at__isnull=False,
                tenant__is_active=True,
            ).first()
            if not domain:
                return failure("website_not_found", "Verified website not found.", 404)
            try:
                organization_id = str(UUID(str(domain.tenant.sso_organization_id)))
                tenant_id = str(UUID(str(domain.tenant.public_id)))
            except (ValueError, TypeError):
                return failure("website_context_unavailable", "Website identity is unavailable.", 503)
            # Both IDs are public routing identifiers. The consumer must still
            # check Commerce and authenticate each customer before opening chat.
            return Response({
                "host": host, "origin": "https://" + host,
                "organization_id": organization_id, "tenant_id": tenant_id,
            }, headers={"Cache-Control": "no-store"})
