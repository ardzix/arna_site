import uuid
from django.db import models


class MediaReference(models.Model):
    """Tenant-scoped record of every file uploaded via Arna File Manager."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file_id = models.UUIDField(unique=True)   # ID from storage API response
    url = models.URLField()                   # Immutable URL — never mutate
    display_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=255, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=50,
        choices=[
            ("upload_pending", "Upload Pending"),
            ("active", "Active"),
            ("aborted", "Aborted"),
            ("deleted", "Deleted"),
        ],
        default="upload_pending",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.display_name
