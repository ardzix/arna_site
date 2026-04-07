from django.db import connection
from rest_framework.permissions import BasePermission

class IsTenantMember(BasePermission):
    """
    Passes if the authenticated SSOUser's tenant_schema matches the
    currently active connection schema (set by TenantMainMiddleware).

    Uses user.tenant_schema (a primitive string) — not the ORM instance.
    """
    def has_permission(self, request, view):
        user = request.user
        if not hasattr(user, "tenant_schema"):
            return False
            
        # connection.tenant is set by TenantMainMiddleware on every request
        return connection.tenant.schema_name == user.tenant_schema
