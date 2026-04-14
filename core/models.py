import uuid
from django.db import models
from django.utils.text import slugify
from django_tenants.models import TenantMixin, DomainMixin


class Tenant(TenantMixin):
    """
    One row = one UMKM/business.
    sso_organization_id links this tenant to an Arna SSO organization.
    """
    sso_organization_id = models.CharField(max_length=255, unique=True, db_index=True)
    name      = models.CharField(max_length=255)
    slug      = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    created_on = models.DateField(auto_now_add=True)

    auto_create_schema = True

    class Meta:
        app_label = "core"

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    """Subdomain or custom domain -> Tenant mapping."""
    class Meta:
        app_label = "core"


# ─── Template Catalog ─────────────────────────────────────────────────────────

class Template(models.Model):
    """
    Master template yang bisa di-clone ke tenant.

    - `source_tenant_schema=None`  → template bawaan sistem
    - `source_tenant_schema='xyz'` → dibuat oleh tenant xyz
    - `is_published=True`          → tampil di katalog publik `/templates/`
    - `is_published=False`         → draft private milik tenant
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=255)
    slug        = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    preview_image_url = models.URLField(blank=True, null=True)
    category    = models.CharField(max_length=100, blank=True)
    is_active   = models.BooleanField(default=True)
    is_published = models.BooleanField(
        default=True,
        help_text="Jika True, tampil di katalog publik /templates/.",
    )
    source_tenant_schema = models.CharField(
        max_length=63, null=True, blank=True, db_index=True,
        help_text="Schema tenant yang membuat template ini. Null = template sistem.",
    )

    class Meta:
        app_label = "core"

    def __str__(self):
        return self.name


class TemplatePage(models.Model):
    """Satu halaman dalam sebuah template (misal: Home, About, Pricing)."""
    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(Template, on_delete=models.CASCADE,
                                 related_name="pages")
    title    = models.CharField(max_length=255)
    slug     = models.SlugField(max_length=255)
    order    = models.PositiveIntegerField(default=0)
    is_home  = models.BooleanField(default=False,
                   help_text="Tandai sebagai halaman utama template.")

    class Meta:
        app_label = "core"
        ordering  = ["order"]
        unique_together = [("template", "slug")]

    def __str__(self):
        return f"{self.template.name} / {self.title}"


class TemplateSection(models.Model):
    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(Template, on_delete=models.CASCADE,
                                 related_name="sections")
    page     = models.ForeignKey(TemplatePage, on_delete=models.CASCADE,
                                 related_name="sections", null=True, blank=True)
    type     = models.CharField(max_length=100)
    order    = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "core"
        ordering  = ["order"]

    def __str__(self):
        return f"{self.template.name} - {self.type}"


class TemplateBlock(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section     = models.ForeignKey(TemplateSection, on_delete=models.CASCADE,
                                    related_name="blocks")
    title       = models.CharField(max_length=500, blank=True)
    subtitle    = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    image_url   = models.URLField(blank=True, null=True)
    extra       = models.JSONField(default=dict, blank=True)
    order       = models.PositiveIntegerField()

    class Meta:
        app_label = "core"
        ordering  = ["order"]

    def __str__(self):
        return getattr(self, "title", str(self.id))


class TemplateListItem(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    block       = models.ForeignKey(TemplateBlock, on_delete=models.CASCADE,
                                    related_name="list_items")
    title       = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    icon        = models.CharField(max_length=100, blank=True)
    order       = models.PositiveIntegerField()

    class Meta:
        app_label = "core"
        ordering  = ["order"]

    def __str__(self):
        return getattr(self, "title", str(self.id))
