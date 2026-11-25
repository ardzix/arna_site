"""Module for core.admin."""
# core/admin.py

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from core.domain_proof_scope import is_pilot_host
from django_tenants.admin import TenantAdminMixin

from core.models import Tenant, Domain, Template, TemplateSection, TemplateBlock, TemplateListItem


@admin.register(Tenant)
class TenantAdmin(TenantAdminMixin, admin.ModelAdmin):
    """TenantAdmin class."""
    list_display = ('name', 'schema_name', 'sso_organization_id', 'is_active', 'created_on')
    search_fields = ('name', 'schema_name')
    list_filter = ('is_active',)

class ScopedDomainAdminForm(forms.ModelForm):
    class Meta:
        model = Domain
        fields = "__all__"

    def clean(self):
        data = super().clean()
        if is_pilot_host(data.get("domain")):
            raise forms.ValidationError("The Arnatech pilot domain requires approved operator proof.")
        return data


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    """DomainAdmin class."""
    list_display = ('domain', 'tenant', 'is_primary')

    form = ScopedDomainAdminForm

    def get_readonly_fields(self, request, obj=None):
        if obj and is_pilot_host(obj.domain):
            return ("domain", "tenant", "role", "status", "verified_at", "verification_method",
                    "verification_token", "crm_tenant", "is_primary", "is_primary_frontend",
                    "target_backend_domain")
        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and is_pilot_host(obj.domain):
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        if any(is_pilot_host(value) for value in queryset.values_list("domain", flat=True)):
            raise PermissionDenied("The Arnatech pilot domain and its audit must be retained.")
        super().delete_queryset(request, queryset)
