# core/admin.py
from django.contrib import admin
from django_tenants.admin import TenantAdminMixin

from .models import Tenant, Domain

@admin.register(Tenant)
class TenantAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'schema_name', 'sso_organization_id', 'is_active')
    search_fields = ('name', 'schema_name', 'sso_organization_id')

@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')