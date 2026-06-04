"""Module for sites.models."""
import uuid

from django.db import models
from django.utils.text import slugify


class Page(models.Model):
    """
    Satu halaman website tenant (misal: Home, About, Pricing).
    Setiap halaman memiliki sekumpulan Section yang membentuk kontennya.
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id    = models.UUIDField(null=True, blank=True, db_index=True)
    title        = models.CharField(max_length=255)
    slug         = models.SlugField(max_length=255)
    is_home      = models.BooleanField(default=False,
                       help_text="Tandai sebagai halaman utama (homepage). Hanya satu per tenant.")
    is_active    = models.BooleanField(default=True)
    order        = models.PositiveIntegerField(default=0)
    meta_title       = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)
    source_template_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Root template UUID used to generate this page.",
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "title"]
        indexes = [
            models.Index(fields=["tenant_id", "slug"]),
            models.Index(fields=["tenant_id", "is_active"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Section(models.Model):
    """Section class."""
    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    page     = models.ForeignKey(Page, on_delete=models.CASCADE,
                                 related_name="sections", null=True, blank=True)
    type     = models.CharField(max_length=100)
    order    = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    template_section_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Section {self.type} - {self.id}"


class ContentBlock(models.Model):
    """ContentBlock class."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section     = models.ForeignKey(Section, on_delete=models.CASCADE,
                                    related_name="blocks")
    title       = models.CharField(max_length=500, blank=True)
    subtitle    = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    image_url   = models.URLField(blank=True)
    extra       = models.JSONField(default=dict, blank=True)
    order       = models.PositiveIntegerField()
    template_block_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return getattr(self, "title", str(self.id))


class ListItem(models.Model):
    """ListItem class."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    block       = models.ForeignKey(ContentBlock, on_delete=models.CASCADE,
                                    related_name="items")
    title       = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    icon        = models.CharField(max_length=100, blank=True)
    order       = models.PositiveIntegerField()
    template_list_item_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return getattr(self, "title", str(self.id))
