import requests as http
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from authentication.permissions import IsTenantMember
from storage.models import MediaReference
from storage.serializers import MediaReferenceSerializer, StorageUploadRequestSerializer

class MediaReferenceViewSet(viewsets.ModelViewSet):
    """
    CRUD for MediaReference objects. Acts as a proxy to the Arna File Manager.
    """
    queryset = MediaReference.objects.all()
    serializer_class = MediaReferenceSerializer
    permission_classes = [IsAuthenticated, IsTenantMember]

    @action(detail=False, methods=['post'], url_path='init-upload', serializer_class=StorageUploadRequestSerializer)
    def init_upload(self, request):
        """
        Proxies request to Arna File Manager to initialize S3 presigned URL,
        saves a 'Pending' file reference, and returns the URL to the client.
        """
        serializer = StorageUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Forward the client's token
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        headers = {"Authorization": auth_header}
        
        storage_base = settings.ARNA_STORAGE_BASE_URL
        
        try:
            resp = http.post(
                f"{storage_base}/api/files/init/", 
                json=serializer.validated_data, 
                headers=headers, 
                timeout=10
            )
            resp.raise_for_status()
        except http.RequestException as e:
            return Response(
                {"error": "Arna File Manager rejected upload initialization."},
                status=status.HTTP_502_BAD_GATEWAY
            )
            
        storage_data = resp.json()
        
        # Save a reference in our tenant DB
        reference = MediaReference.objects.create(
            file_id=storage_data["file_id"],
            url=storage_data["url"],
            display_name=serializer.validated_data["display_name"],
            mime_type=serializer.validated_data["mime_type"],
            size_bytes=serializer.validated_data["size_bytes"],
            status="upload_pending"
        )
        
        return Response({
            "reference_id": reference.id,
            "upload_url": storage_data.get("upload_url"),
            "file_id": storage_data["file_id"],
            "url": storage_data["url"]
        }, status=status.HTTP_201_CREATED)
        
    @action(detail=True, methods=['post'], url_path='confirm-upload')
    def confirm_upload(self, request, pk=None):
        reference = self.get_object()
        
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        headers = {"Authorization": auth_header}
        storage_base = settings.ARNA_STORAGE_BASE_URL
        
        try:
            resp = http.post(
                f"{storage_base}/api/files/{reference.file_id}/confirm/", 
                headers=headers, 
                timeout=10
            )
            resp.raise_for_status()
        except http.RequestException:
            return Response({"error": "Failed to confirm with File Manager"}, status=status.HTTP_400_BAD_REQUEST)
                         
        reference.status = "active"
        reference.save()
        return Response(self.get_serializer(reference).data)
