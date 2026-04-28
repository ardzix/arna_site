import requests as http
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

from authentication.permissions import IsTenantMember, IsTenantAdmin, IsTenantOwner
from storage.models import MediaReference
from storage.serializers import (
    MediaReferenceSerializer,
    StorageUploadRequestSerializer,
    StoragePresignRequestSerializer,
    StorageCompleteRequestSerializer,
)

READ_ACTIONS = {'list', 'retrieve'}


def _read_permissions():
    return [IsAuthenticated(), IsTenantMember()]


def _write_permissions():
    return [IsAuthenticated(), IsTenantMember(), (IsTenantAdmin | IsTenantOwner)()]


_init_upload_response = openapi.Response(
    description='Upload berhasil diinisiasi. Gunakan `multipart` info untuk upload langsung ke S3.',
    examples={
        'application/json': {
            'reference_id': 'uuid-referensi-lokal',
            'file_id': 'file-id-dari-fm',
            'url': 'https://storage.arnatech.id/files/...',
            'multipart': {
                'upload_id': 's3-multipart-upload-id',
                'parts': [{'part_number': 1, 'presign_url': 'https://s3.amazonaws.com/...'}],
            },
        }
    },
)

_presign_response = openapi.Response(
    description='URL presigned untuk setiap part yang diminta.',
    examples={
        'application/json': {
            'parts': [
                {'part_number': 1, 'presign_url': 'https://s3.amazonaws.com/...?X-Amz-Signature=...'},
                {'part_number': 2, 'presign_url': 'https://s3.amazonaws.com/...?X-Amz-Signature=...'},
            ]
        }
    },
)


class MediaReferenceViewSet(viewsets.ModelViewSet):
    """
    Manajemen referensi file media yang tersimpan di Arna File Manager (S3).

    Endpoint ini bertindak sebagai **proxy** antara tenant dan Arna File Manager.
    Record `MediaReference` disimpan lokal di schema tenant sebagai referensi,
    sementara file fisik disimpan di S3 melalui File Manager.

    **Flow upload multipart:**
    1. `POST /files/init-upload/` — Inisiasi upload, dapat `file_id` dan info multipart.
    2. `PUT <presign_url>` — Upload setiap part langsung ke S3 (tanpa melewati server ini).
    3. `POST /files/{id}/presign/` — Jika butuh URL presigned tambahan untuk part berikutnya.
    4. `POST /files/{id}/complete/` — Konfirmasi upload selesai, status berubah ke `active`.
    5. `POST /files/{id}/abort/` — Batalkan upload jika terjadi error.

    **Permission:**
    - **GET** (list/detail): semua member tenant.
    - **POST/PATCH/DELETE** dan semua aksi upload: hanya `site_admin` atau owner.
    """
    queryset = MediaReference.objects.all()
    serializer_class = MediaReferenceSerializer

    def get_permissions(self):
        if self.action in READ_ACTIONS:
            return _read_permissions()
        return _write_permissions()

    def _get_fm_headers(self, request):
        return {"Authorization": request.META.get("HTTP_AUTHORIZATION", "")}

    @swagger_auto_schema(
        operation_summary='Inisiasi upload file baru',
        operation_description=(
            'Mendaftarkan file baru ke Arna File Manager dan mendapatkan informasi '
            'multipart upload (upload_id + presigned URLs untuk setiap part). '
            'Setelah ini, upload setiap part langsung ke S3 menggunakan presigned URL. '
            'Selesaikan dengan `POST /files/{id}/complete/`.'
        ),
        request_body=StorageUploadRequestSerializer,
        responses={
            201: _init_upload_response,
            400: openapi.Response(description='Request tidak valid.'),
            502: openapi.Response(description='Arna File Manager tidak dapat dihubungi.'),
        },
        security=[{'Bearer': []}],
    )
    @action(detail=False, methods=['post'], url_path='init-upload',
            serializer_class=StorageUploadRequestSerializer)
    def init_upload(self, request):
        serializer = StorageUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        headers      = self._get_fm_headers(request)
        storage_base = settings.ARNA_STORAGE_BASE_URL

        try:
            resp = http.post(
                f"{storage_base}/api/files/upload",
                json=serializer.validated_data,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
        except http.RequestException as e:
            return Response(
                {"error": f"Arna File Manager rejected upload init: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            storage_data = resp.json()
        except ValueError:
            body_preview = (resp.text or "")[:300]
            return Response(
                {
                    "error": "Arna File Manager returned non-JSON response on upload init.",
                    "upstream_body": body_preview,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        file_id = storage_data.get("file_id")
        file_url = storage_data.get("url")
        if not file_id or not file_url:
            return Response(
                {
                    "error": "Arna File Manager response missing required fields: file_id/url.",
                    "upstream_response": storage_data,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            reference = MediaReference.objects.create(
                file_id=file_id,
                url=file_url,
                display_name=serializer.validated_data["filename"],
                mime_type=serializer.validated_data["mime_type"],
                size_bytes=serializer.validated_data["size_bytes"],
                status="upload_pending",
            )
        except Exception as e:
            return Response(
                {"error": f"Failed saving media reference: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({
            "reference_id": reference.id,
            "multipart":    storage_data.get("multipart"),
            "file_id":      file_id,
            "url":          file_url,
        }, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        operation_summary='Dapatkan URL presigned untuk upload part',
        operation_description=(
            'Meminta URL presigned baru untuk part-part tertentu dari multipart upload. '
            'Kirimkan array nomor part yang ingin di-presign.'
        ),
        request_body=StoragePresignRequestSerializer,
        responses={
            200: _presign_response,
            502: openapi.Response(description='Gagal menghubungi Arna File Manager.'),
        },
        security=[{'Bearer': []}],
    )
    @action(detail=True, methods=['post'], url_path='presign',
            serializer_class=StoragePresignRequestSerializer)
    def presign(self, request, pk=None):
        reference = self.get_object()
        serializer = StoragePresignRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        headers      = self._get_fm_headers(request)
        storage_base = settings.ARNA_STORAGE_BASE_URL

        try:
            resp = http.post(
                f"{storage_base}/api/files/{reference.file_id}/parts/presign",
                json=serializer.validated_data,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
        except http.RequestException:
            return Response(
                {"error": "Failed to get presigned URLs from FM"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(resp.json(), status=200)

    @swagger_auto_schema(
        operation_summary='Selesaikan multipart upload',
        operation_description=(
            'Memberi tahu Arna File Manager bahwa semua part telah berhasil diupload ke S3. '
            'File Manager akan menggabungkan semua part menjadi satu file. '
            'Status `MediaReference` akan berubah menjadi `active`.'
        ),
        request_body=StorageCompleteRequestSerializer,
        responses={
            200: openapi.Response(
                description='Upload selesai. MediaReference dikembalikan dengan status `active`.',
                schema=MediaReferenceSerializer(),
            ),
            400: openapi.Response(description='Gagal menyelesaikan upload di File Manager.'),
        },
        security=[{'Bearer': []}],
    )
    @action(detail=True, methods=['post'], url_path='complete',
            serializer_class=StorageCompleteRequestSerializer)
    def complete_upload(self, request, pk=None):
        reference = self.get_object()
        serializer = StorageCompleteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        headers      = self._get_fm_headers(request)
        storage_base = settings.ARNA_STORAGE_BASE_URL

        try:
            resp = http.post(
                f"{storage_base}/api/files/{reference.file_id}/complete",
                json=serializer.validated_data,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
        except http.RequestException:
            return Response(
                {"error": "Failed to complete upload with File Manager"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reference.status = "active"
        reference.save()
        return Response(MediaReferenceSerializer(reference).data)

    @swagger_auto_schema(
        operation_summary='Batalkan multipart upload',
        operation_description=(
            'Membatalkan multipart upload yang sedang berjalan dan membersihkan resource S3. '
            'Status `MediaReference` akan berubah menjadi `aborted`.'
        ),
        responses={
            200: openapi.Response(
                description='Upload dibatalkan.',
                examples={'application/json': {'status': 'aborted'}},
            ),
            502: openapi.Response(description='Gagal menghubungi Arna File Manager.'),
        },
        security=[{'Bearer': []}],
    )
    @action(detail=True, methods=['post'], url_path='abort')
    def abort(self, request, pk=None):
        reference = self.get_object()
        headers      = self._get_fm_headers(request)
        storage_base = settings.ARNA_STORAGE_BASE_URL

        try:
            resp = http.post(
                f"{storage_base}/api/files/{reference.file_id}/abort",
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
        except http.RequestException:
            return Response(
                {"error": "Failed to abort upload with File Manager"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        reference.status = "aborted"
        reference.save()
        return Response({"status": "aborted"})

    def perform_destroy(self, instance):
        """Hapus file dari Arna File Manager sebelum menghapus record lokal."""
        headers      = self._get_fm_headers(self.request)
        storage_base = settings.ARNA_STORAGE_BASE_URL
        try:
            resp = http.delete(
                f"{storage_base}/api/files/{instance.file_id}",
                headers=headers,
                timeout=10,
            )
            if resp.status_code not in [204, 404]:
                resp.raise_for_status()
        except http.RequestException:
            from rest_framework.exceptions import APIException
            raise APIException("Failed to delete file from remote Arna File Manager.")

        instance.delete()
