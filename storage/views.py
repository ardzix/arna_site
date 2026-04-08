import requests as http
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from authentication.permissions import IsTenantMember
from storage.models import MediaReference
from storage.serializers import (
    MediaReferenceSerializer, 
    StorageUploadRequestSerializer,
    StoragePresignRequestSerializer,
    StorageCompleteRequestSerializer
)

class MediaReferenceViewSet(viewsets.ModelViewSet):
    """
    CRUD for MediaReference objects. Acts as a proxy to the Arna File Manager.
    """
    queryset = MediaReference.objects.all()
    serializer_class = MediaReferenceSerializer
    permission_classes = [IsAuthenticated, IsTenantMember]

    def _get_fm_headers(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        return {"Authorization": auth_header}

    @action(detail=False, methods=['post'], url_path='init-upload', serializer_class=StorageUploadRequestSerializer)
    def init_upload(self, request):
        """
        Proxies request to Arna File Manager to initialize S3 multipart upload,
        saves a 'Pending' file reference, and returns the payload to the client.
        """
        serializer = StorageUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        headers = self._get_fm_headers(request)
        storage_base = settings.ARNA_STORAGE_BASE_URL
        
        try:
            resp = http.post(
                f"{storage_base}/api/files/upload", 
                json=serializer.validated_data, 
                headers=headers, 
                timeout=10
            )
            resp.raise_for_status()
        except http.RequestException as e:
            return Response(
                {"error": f"Arna File Manager rejected upload init: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY
            )
            
        storage_data = resp.json()
        
        reference = MediaReference.objects.create(
            file_id=storage_data["file_id"],
            url=storage_data["url"],
            display_name=serializer.validated_data["filename"],
            mime_type=serializer.validated_data["mime_type"],
            size_bytes=serializer.validated_data["size_bytes"],
            status="upload_pending"
        )
        
        return Response({
            "reference_id": reference.id,
            "multipart": storage_data.get("multipart"),
            "file_id": storage_data["file_id"],
            "url": storage_data["url"]
        }, status=status.HTTP_201_CREATED)
        
    @action(detail=True, methods=['post'], url_path='presign', serializer_class=StoragePresignRequestSerializer)
    def presign(self, request, pk=None):
        reference = self.get_object()
        serializer = StoragePresignRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        headers = self._get_fm_headers(request)
        storage_base = settings.ARNA_STORAGE_BASE_URL
        
        try:
            resp = http.post(
                f"{storage_base}/api/files/{reference.file_id}/parts/presign", 
                json=serializer.validated_data,
                headers=headers, 
                timeout=10
            )
            resp.raise_for_status()
        except http.RequestException:
            return Response({"error": "Failed to get presigned URLs from FM"}, status=status.HTTP_502_BAD_GATEWAY)
            
        return Response(resp.json(), status=200)

    @action(detail=True, methods=['post'], url_path='complete', serializer_class=StorageCompleteRequestSerializer)
    def complete_upload(self, request, pk=None):
        reference = self.get_object()
        serializer = StorageCompleteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        headers = self._get_fm_headers(request)
        storage_base = settings.ARNA_STORAGE_BASE_URL
        
        try:
            resp = http.post(
                f"{storage_base}/api/files/{reference.file_id}/complete", 
                json=serializer.validated_data,
                headers=headers, 
                timeout=10
            )
            resp.raise_for_status()
        except http.RequestException:
            return Response({"error": "Failed to complete upload with File Manager"}, status=status.HTTP_400_BAD_REQUEST)
                         
        reference.status = "active"
        reference.save()
        return Response(MediaReferenceSerializer(reference).data)

    @action(detail=True, methods=['post'], url_path='abort')
    def abort(self, request, pk=None):
        reference = self.get_object()
        headers = self._get_fm_headers(request)
        storage_base = settings.ARNA_STORAGE_BASE_URL
        
        try:
            resp = http.post(
                f"{storage_base}/api/files/{reference.file_id}/abort", 
                headers=headers, 
                timeout=10
            )
            resp.raise_for_status()
        except http.RequestException:
            return Response({"error": "Failed to abort upload with File Manager"}, status=status.HTTP_502_BAD_GATEWAY)
            
        reference.status = "aborted"
        reference.save()
        return Response({"status": "aborted"})

    def perform_destroy(self, instance):
        headers = self._get_fm_headers(self.request)
        storage_base = settings.ARNA_STORAGE_BASE_URL
        try:
            resp = http.delete(f"{storage_base}/api/files/{instance.file_id}", headers=headers, timeout=10)
            if resp.status_code not in [204, 404]:
                resp.raise_for_status()
        except http.RequestException:
            from rest_framework.exceptions import APIException
            raise APIException("Failed to delete file from remote Arna File Manager.")
            
        instance.delete()
