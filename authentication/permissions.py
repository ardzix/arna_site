"""Module for authentication.permissions."""
from django.db import connection

from rest_framework.permissions import BasePermission

class IsTenantMember(BasePermission):
    """
    Passes if the authenticated SSOUser belongs to the same organization
    as the active tenant context.

    Why org-level check:
    - One organization can own multiple tenants.
    - `tenant_schema` can be stale when auth user object is cached from a
      different host request.

    Legacy fallback:
    - If org comparison is not available, schema comparison is still used.
    """
    message = "Permission denied for this tenant."

    def has_permission(self, request, view):
        user = request.user
        if not hasattr(user, "tenant_schema"):
            return False

        # connection.tenant is set by TenantMainMiddleware on every request
        tenant = getattr(connection, 'tenant', None)
        if not tenant:
            return False

        user_org_id = str(getattr(user, "org_id", "") or "")
        tenant_org_id = str(getattr(tenant, "sso_organization_id", "") or "")
        if user_org_id and tenant_org_id:
            return user_org_id == tenant_org_id

        return tenant.schema_name == user.tenant_schema

class IsTenantAdmin(BasePermission):
    """Preserve site_admin; also honor an org-bound, signed CMS grant.

    The permission branch requires both organization IDs, even for legacy
    requests where IsTenantMember can fall back to the shared schema name.
    """
    def has_permission(self, request, view):
        user = request.user
        roles = getattr(user, 'roles', [])
        if isinstance(roles, list) and 'site_admin' in roles:
            return True
        grants = getattr(user, 'permissions', [])
        if (getattr(user, 'is_authenticated', False) is not True
                or not isinstance(grants, list)
                or 'arnasite.cms.manage' not in grants):
            return False
        tenant = getattr(connection, 'tenant', None)
        user_org = str(getattr(user, 'org_id', '') or '')
        tenant_org = str(getattr(tenant, 'sso_organization_id', '') or '')
        return bool(user_org and tenant_org and user_org == tenant_org)

class IsTenantOwner(BasePermission):
    """
    Passes only if:
    User is_owner == True (JWT claim 'is_owner')
    Owner adalah super-admin otomatis tanpa perlu role assignment.
    """
    def has_permission(self, request, view):
        user = request.user
        return getattr(user, 'is_owner', False) is True
