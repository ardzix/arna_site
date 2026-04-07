import uuid
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Tenant(TenantMixin):
    """
    One row = one UMKM/business.
    sso_organization_id links this tenant to an Arna SSO organization.
    """
    sso_organization_id = models.CharField(max_length=255, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    created_on = models.DateField(auto_now_add=True)

    auto_create_schema = True  # django-tenants: auto-create PG schema on save

    class Meta:
        app_label = "core"

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    """Subdomain or custom domain -> Tenant mapping."""
    class Meta:
        app_label = "core"


# ─── Template Catalog (global, immutable) ─────────────────────────────────────

class Template(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    preview_image_url = models.URLField(blank=True, null=True)
    category = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "core"

    def __str__(self):
        return self.name


class TemplateSection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(Template, on_delete=models.CASCADE,
                                 related_name="sections")
    type = models.CharField(max_length=100)   # e.g. "hero", "features", "contact"
    order = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "core"
        ordering = ["order"]

    def __str__(self):
        return f"{self.template.name} - {self.type}"


class TemplateBlock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(TemplateSection, on_delete=models.CASCADE,
                                related_name="blocks")
    title = models.CharField(max_length=500, blank=True)
    subtitle = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True, null=True)
    extra = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField()

    class Meta:
        app_label = "core"
        ordering = ["order"]

    def __str__(self):
        return getattr(self, "title", str(self.id))


class TemplateListItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    block = models.ForeignKey(TemplateBlock, on_delete=models.CASCADE,
                              related_name="list_items")
    title = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=100, blank=True)
    order = models.PositiveIntegerField()

    class Meta:
        app_label = "core"
        ordering = ["order"]

    def __str__(self):
        return getattr(self, "title", str(self.id))