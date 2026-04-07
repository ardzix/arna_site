from django.db import models

class Section(models.Model):
    # Link back to the original TemplateSection
    template_section_id = models.IntegerField(null=True, blank=True) 
    
    type = models.CharField(max_length=100)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

class ContentBlock(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='blocks')
    template_block_id = models.IntegerField(null=True, blank=True)
    
    title = models.CharField(max_length=255, blank=True)
    subtitle = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True, null=True)
    extra = models.JSONField(default=dict, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

class ListItem(models.Model):
    block = models.ForeignKey(ContentBlock, on_delete=models.CASCADE, related_name='list_items')
    template_list_item_id = models.IntegerField(null=True, blank=True)
    
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=100, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

class MediaReference(models.Model):
    """
    Stores metadata for files uploaded via the Arna File Manager workflow.
    No files are stored locally.
    """
    file_id = models.UUIDField(unique=True) # Maps to Arna File Manager file_id
    url = models.URLField()                 # Immutable URL from storage
    display_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=255)
    size_bytes = models.BigIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.display_name