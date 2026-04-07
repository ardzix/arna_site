# core/models.py
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin

class Tenant(TenantMixin):
    """
    The main tenant model. Each instance of this represents a unique Client/UMKM.
    This data lives purely in the public schema.
    """
    # CRITICAL: Maps directly to Arna SSO (PRD Requirement 5)
    sso_organization_id = models.CharField(max_length=255, unique=True, db_index=True)
    
    name = models.CharField(max_length=100)
    
    # PRD Requirement 12: Tenant deletion should be a soft delete
    is_active = models.BooleanField(default=True) 
    created_on = models.DateTimeField(auto_now_add=True)

    # When a Tenant is saved, django-tenants will automatically generate the PostgreSQL schema
    auto_create_schema = True

    def __str__(self):
        return self.name

class Domain(DomainMixin):
    """
    Routes incoming requests to the correct Tenant schema based on the domain/subdomain.
    e.g., tenant1.bisnisnaikkelas.com -> maps to Tenant 1
    """
    pass

class Template(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    preview_image_url = models.URLField(blank=True, null=True)
    category = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class TemplateSection(models.Model):
    template = models.ForeignKey(Template, on_delete=models.CASCADE, related_name='sections')
    type = models.CharField(max_length=100)  # e.g., 'hero', 'footer', 'pricing'
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']

class TemplateBlock(models.Model):
    section = models.ForeignKey(TemplateSection, on_delete=models.CASCADE, related_name='blocks')
    title = models.CharField(max_length=255, blank=True)
    subtitle = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True, null=True)
    
    # PRD Requirement: Strict structured content. 
    # Use this JSON field to store specific configuration (e.g., button text, alignment)
    extra = models.JSONField(default=dict, blank=True) 
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

class TemplateListItem(models.Model):
    block = models.ForeignKey(TemplateBlock, on_delete=models.CASCADE, related_name='list_items')
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=100, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']