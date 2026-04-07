from rest_framework import serializers
from storage.models import MediaReference

class MediaReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaReference
        fields = ["id", "file_id", "url", "display_name", "mime_type", "size_bytes", "status", "created_at"]
        read_only_fields = ["id", "file_id", "url", "status", "created_at"]

class StorageUploadRequestSerializer(serializers.Serializer):
    # Proxy payload payload specific to S3 direct upload initialization
    display_name = serializers.CharField(max_length=255)
    mime_type = serializers.CharField(max_length=255)
    size_bytes = serializers.IntegerField()
