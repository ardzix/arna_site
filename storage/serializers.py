from rest_framework import serializers
from storage.models import MediaReference

class MediaReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaReference
        fields = ["id", "file_id", "url", "display_name", "mime_type", "size_bytes", "status", "created_at"]
        read_only_fields = ["id", "file_id", "url", "status", "created_at"]

class StorageUploadRequestSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=255)
    mime_type = serializers.CharField(max_length=255)
    size_bytes = serializers.IntegerField()
    owner_scope = serializers.ChoiceField(choices=["user", "org"], default="org")
    visibility = serializers.ChoiceField(choices=["private", "org", "public", "shared"], default="private")

    def validate_mime_type(self, value):
        # Enforce standard MIME format (example: image/png) to avoid
        # upstream storage rejection or ambiguous content type handling.
        if "/" not in value:
            raise serializers.ValidationError("mime_type harus format valid, contoh: image/png")
        return value

class StoragePresignRequestSerializer(serializers.Serializer):
    parts = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False
    )
    
class StorageCompletePartSerializer(serializers.Serializer):
    part_number = serializers.IntegerField(min_value=1)
    etag = serializers.CharField(max_length=255)

class StorageCompleteRequestSerializer(serializers.Serializer):
    parts = serializers.ListField(
        child=StorageCompletePartSerializer(),
        allow_empty=False
    )
