# core/admin.py
from django.contrib import admin
from django_tenants.admin import TenantAdminMixin

from core.models import Tenant, Domain, Template, TemplateSection, TemplateBlock, TemplateListItem


@admin.register(Tenant)
class TenantAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'schema_name', 'sso_organization_id', 'is_active', 'created_on')
    search_fields = ('name', 'schema_name')
    list_filter = ('is_active',)

@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'tenant', 'is_primary')