import uuid
from django.db import models


class Section(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=100)    # e.g. "hero", "about", "team"
    order = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    template_section_id = models.UUIDField(null=True, blank=True)  # origin ref

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Section {self.type} - {self.id}"


class ContentBlock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(Section, on_delete=models.CASCADE,
                                related_name="blocks")
    title = models.CharField(max_length=500, blank=True)
    subtitle = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    extra = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField()
    template_block_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return getattr(self, "title", str(self.id))


class ListItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    block = models.ForeignKey(ContentBlock, on_delete=models.CASCADE,
                              related_name="items")
    title = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=100, blank=True)
    order = models.PositiveIntegerField()
    template_list_item_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return getattr(self, "title", str(self.id))