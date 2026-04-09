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
        tenant = getattr(connection, 'tenant', None)
        if not tenant:
            return False
            
        return tenant.schema_name == user.tenant_schema

class IsTenantAdmin(BasePermission):
    """
    Passes only if:
    1. User is authenticated (has SSOUser)
    2. User has 'site_admin' in their roles (dari JWT claim)
    """
    def has_permission(self, request, view):
        user = request.user
        if not hasattr(user, 'roles'):
            return False
        return 'site_admin' in user.roles

class IsTenantOwner(BasePermission):
    """
    Passes only if:
    User is_owner == True (JWT claim 'is_owner')
    Owner adalah super-admin otomatis tanpa perlu role assignment.
    """
    def has_permission(self, request, view):
        user = request.user
        return getattr(user, 'is_owner', False) is True
