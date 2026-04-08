from django.test import TestCase
from django_tenants.test.client import TenantClient
from unittest.mock import patch
import uuid
from core.models import Tenant, Domain


def _make_auth_mock(org_id_str):
    class MockMe:
        def json(self): return {"id": str(uuid.uuid4()), "email": "user@arna.com"}
        def raise_for_status(self): pass

    class MockOrg:
        def json(self): return {"id": org_id_str}
        def raise_for_status(self): pass

    def side_effect(url, *args, **kwargs):
        if "auth/me" in url: return MockMe()
        elif "organizations/current" in url: return MockOrg()
        raise Exception(f"Unmocked URL: {url}")

    return side_effect


class StorageProxyTest(TestCase):
    def setUp(self):
        from django.db import connection
        connection.set_schema_to_public()

        self.org_id = uuid.uuid4()
        self.tenant = Tenant.objects.create(
            schema_name='tenant_storage_test', name='Storage',
            slug='st', sso_organization_id=self.org_id
        )
        Domain.objects.create(domain='storage.localhost', tenant=self.tenant, is_primary=True)

    @patch('storage.views.http.post')
    @patch('authentication.backends.http.get')
    def test_storage_init_upload(self, mock_auth_get, mock_storage_post):
        """init-upload proxies to File Manager, saves a pending reference, returns 201."""
        mock_auth_get.side_effect = _make_auth_mock(str(self.org_id))

        storage_file_id = str(uuid.uuid4())

        class MockStorageResp:
            status_code = 200
            def json(self): return {
                "file_id": storage_file_id,
                "url": "https://s3.arna/file.jpg",
                "status": "upload_pending",
                "multipart": {
                    "upload_id": "abc123",
                    "part_size_bytes": 8388608,
                    "expires_at": "2026-12-31T00:00:00Z"
                }
            }
            def raise_for_status(self): pass

        mock_storage_post.return_value = MockStorageResp()

        client = TenantClient(self.tenant)
        response = client.post(
            "/api/storage/files/init-upload/",
            {"filename": "logo.png", "mime_type": "image/png", "size_bytes": 1024},
            HTTP_AUTHORIZATION="Bearer unique_storage_token",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201,
                         f"init-upload failed: {response.content}")
        data = response.json()
        self.assertEqual(data["file_id"], storage_file_id)
        self.assertIn("multipart", data)
        self.assertIn("upload_id", data["multipart"])

        # Verify DB state — reference is 'upload_pending'
        from django.db import connection
        connection.set_tenant(self.tenant)
        from storage.models import MediaReference
        ref = MediaReference.objects.get(id=data["reference_id"])
        self.assertEqual(ref.status, "upload_pending")

    @patch('storage.views.http.post')
    @patch('authentication.backends.http.get')
    def test_complete_upload_marks_active(self, mock_auth_get, mock_storage_post):
        """complete action calls File Manager and sets reference status to 'active'."""
        mock_auth_get.side_effect = _make_auth_mock(str(self.org_id))

        storage_file_id = str(uuid.uuid4())

        class MockInitResp:
            status_code = 200
            def json(self): return {
                "file_id": storage_file_id,
                "url": "https://s3.arna/file.jpg",
                "status": "upload_pending",
                "multipart": {"upload_id": "abc123", "part_size_bytes": 8388608},
            }
            def raise_for_status(self): pass

        class MockCompleteResp:
            status_code = 200
            def json(self): return {"file_id": storage_file_id, "status": "active"}
            def raise_for_status(self): pass

        # First call = init, second call = complete
        mock_storage_post.side_effect = [MockInitResp(), MockCompleteResp()]

        client = TenantClient(self.tenant)
        auth = {"HTTP_AUTHORIZATION": "Bearer storage_token"}

        # Init upload
        init_resp = client.post(
            "/api/storage/files/init-upload/",
            {"filename": "logo.png", "mime_type": "image/png", "size_bytes": 512},
            content_type="application/json", **auth
        )
        self.assertEqual(init_resp.status_code, 201)
        ref_id = init_resp.json()["reference_id"]

        # Complete upload (step 4)
        complete_resp = client.post(
            f"/api/storage/files/{ref_id}/complete/",
            {"parts": [{"part_number": 1, "etag": '"abc123"'}]},
            content_type="application/json", **auth
        )
        self.assertEqual(complete_resp.status_code, 200)
        self.assertEqual(complete_resp.json()["status"], "active")

    @patch('storage.views.http.post')
    @patch('authentication.backends.http.get')
    def test_file_manager_502_handled(self, mock_auth_get, mock_storage_post):
        """When File Manager is down, init-upload should return 502 gracefully."""
        mock_auth_get.side_effect = _make_auth_mock(str(self.org_id))

        import requests
        mock_storage_post.side_effect = requests.RequestException("File Manager down")

        client = TenantClient(self.tenant)
        response = client.post(
            "/api/storage/files/init-upload/",
            {"filename": "logo.png", "mime_type": "image/png", "size_bytes": 1024},
            HTTP_AUTHORIZATION="Bearer token",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 502)

    @patch('storage.views.http.post')
    @patch('authentication.backends.http.get')
    def test_storage_presign_proxies_to_file_manager(self, mock_auth_get, mock_storage_post):
        """presign endpoint calls File Manager and returns presigned URLs."""
        mock_auth_get.side_effect = _make_auth_mock(str(self.org_id))

        storage_file_id = str(uuid.uuid4())

        class MockPresignResp:
            status_code = 200
            def json(self): return {
                "file_id": storage_file_id,
                "parts": [{"part_number": 1, "url": "https://s3.local/part1"}]
            }
            def raise_for_status(self): pass

        mock_storage_post.return_value = MockPresignResp()

        # Create a pending reference
        from django.db import connection
        connection.set_tenant(self.tenant)
        from storage.models import MediaReference
        ref = MediaReference.objects.create(
            file_id=storage_file_id, url=f"https://f.com/{storage_file_id}",
            display_name="x", mime_type="x", size_bytes=10, status="upload_pending"
        )

        client = TenantClient(self.tenant)
        response = client.post(
            f"/api/storage/files/{ref.id}/presign/",
            {"parts": [1]},
            HTTP_AUTHORIZATION="Bearer token",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["parts"][0]["url"], "https://s3.local/part1")

    @patch('storage.views.http.post')
    @patch('authentication.backends.http.get')
    def test_storage_abort_sets_aborted_status(self, mock_auth_get, mock_storage_post):
        """abort endpoint calls File Manager and sets reference to aborted."""
        mock_auth_get.side_effect = _make_auth_mock(str(self.org_id))

        class MockAbortResp:
            status_code = 200
            def raise_for_status(self): pass

        mock_storage_post.return_value = MockAbortResp()

        # Create a pending reference
        storage_file_id = str(uuid.uuid4())
        from django.db import connection
        connection.set_tenant(self.tenant)
        from storage.models import MediaReference
        ref = MediaReference.objects.create(
            file_id=storage_file_id, url=f"https://f.com/{storage_file_id}",
            display_name="x", mime_type="x", size_bytes=10, status="upload_pending"
        )

        client = TenantClient(self.tenant)
        response = client.post(
            f"/api/storage/files/{ref.id}/abort/",
            {},
            HTTP_AUTHORIZATION="Bearer token",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "aborted")

        ref.refresh_from_db()
        self.assertEqual(ref.status, "aborted")

    @patch('storage.views.http.delete')
    @patch('authentication.backends.http.get')
    def test_storage_destroy_calls_file_manager_delete(self, mock_auth_get, mock_storage_delete):
        """Deleting a MediaReference calls the File Manager DELETE API."""
        mock_auth_get.side_effect = _make_auth_mock(str(self.org_id))

        class MockDeleteResp:
            status_code = 204
            def raise_for_status(self): pass

        mock_storage_delete.return_value = MockDeleteResp()

        # Create an active reference
        storage_file_id = str(uuid.uuid4())
        from django.db import connection
        connection.set_tenant(self.tenant)
        from storage.models import MediaReference
        ref = MediaReference.objects.create(
            file_id=storage_file_id, url=f"https://f.com/{storage_file_id}",
            display_name="x", mime_type="x", size_bytes=10, status="active"
        )

        client = TenantClient(self.tenant)
        response = client.delete(
            f"/api/storage/files/{ref.id}/",
            HTTP_AUTHORIZATION="Bearer token"
        )
        self.assertEqual(response.status_code, 204)

        # Ensure object is actually deleted from DB
        self.assertFalse(MediaReference.objects.filter(id=ref.id).exists())
