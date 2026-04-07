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
                "upload_url": "https://s3.arna/presigned-url",
            }
            def raise_for_status(self): pass

        mock_storage_post.return_value = MockStorageResp()

        client = TenantClient(self.tenant)
        response = client.post(
            "/api/storage/files/init-upload/",
            {"display_name": "Logo", "mime_type": "image/png", "size_bytes": 1024},
            HTTP_AUTHORIZATION="Bearer unique_storage_token",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201,
                         f"init-upload failed: {response.content}")
        data = response.json()
        self.assertEqual(data["file_id"], storage_file_id)
        self.assertEqual(data["upload_url"], "https://s3.arna/presigned-url")

        # Verify DB state — reference is 'upload_pending'
        from django.db import connection
        connection.set_tenant(self.tenant)
        from storage.models import MediaReference
        ref = MediaReference.objects.get(id=data["reference_id"])
        self.assertEqual(ref.status, "upload_pending")

    @patch('storage.views.http.post')
    @patch('authentication.backends.http.get')
    def test_confirm_upload_marks_active(self, mock_auth_get, mock_storage_post):
        """confirm-upload calls File Manager and sets reference status to 'active'."""
        mock_auth_get.side_effect = _make_auth_mock(str(self.org_id))

        storage_file_id = str(uuid.uuid4())

        class MockInitResp:
            status_code = 200
            def json(self): return {
                "file_id": storage_file_id,
                "url": "https://s3.arna/file.jpg",
                "upload_url": "https://s3.arna/presigned-url",
            }
            def raise_for_status(self): pass

        class MockConfirmResp:
            status_code = 200
            def json(self): return {"status": "confirmed"}
            def raise_for_status(self): pass

        # First call = init, second call = confirm
        mock_storage_post.side_effect = [MockInitResp(), MockConfirmResp()]

        client = TenantClient(self.tenant)
        auth = {"HTTP_AUTHORIZATION": "Bearer storage_token"}

        # Init upload
        init_resp = client.post(
            "/api/storage/files/init-upload/",
            {"display_name": "Logo", "mime_type": "image/png", "size_bytes": 512},
            content_type="application/json", **auth
        )
        self.assertEqual(init_resp.status_code, 201)
        ref_id = init_resp.json()["reference_id"]

        # Confirm upload
        confirm_resp = client.post(
            f"/api/storage/files/{ref_id}/confirm-upload/",
            content_type="application/json", **auth
        )
        self.assertEqual(confirm_resp.status_code, 200)
        self.assertEqual(confirm_resp.json()["status"], "active")

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
            {"display_name": "Logo", "mime_type": "image/png", "size_bytes": 1024},
            HTTP_AUTHORIZATION="Bearer token",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 502)
