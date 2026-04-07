from django.test import TestCase, Client
from unittest.mock import patch
import uuid
from core.models import Tenant, Domain

class StorageProxyTest(TestCase):
    def setUp(self):
        from django.db import connection
        connection.set_schema_to_public()
        
        self.org_id = uuid.uuid4()
        self.tenant = Tenant.objects.create(
            schema_name='tenant_storage_test', 
            name='Storage', 
            slug='st', 
            sso_organization_id=self.org_id
        )
        Domain.objects.create(domain='storage.localhost', tenant=self.tenant, is_primary=True)

    @patch('storage.views.http.post')
    @patch('authentication.backends.http.get')
    def test_storage_init_upload(self, mock_auth_get, mock_storage_post):
        # Auth Mocks
        org_id_str = str(self.org_id)
        class MockMeResponse:
            def json(self): return {"id": str(uuid.uuid4()), "email": "user@arna.com"}
            def raise_for_status(self): pass
        class MockOrgResponse:
            def json(self): return {"id": org_id_str}
            def raise_for_status(self): pass
            
        mock_auth_get.side_effect = lambda url, *a, **kw: MockMeResponse() if "auth/me" in url else MockOrgResponse()

        # Storage Mock
        storage_file_id = str(uuid.uuid4())
        class MockStorageResponse:
            status_code = 200
            def json(self): return {
                "file_id": storage_file_id, 
                "url": "https://s3.arna/file.jpg", 
                "upload_url": "https://s3.arna/presigned..."
            }
            def raise_for_status(self): pass
        mock_storage_post.return_value = MockStorageResponse()

        client = Client(HTTP_HOST='storage.localhost')
        response = client.post(
            "/api/storage/files/init-upload/",
            {"display_name": "Logo", "mime_type": "image/png", "size_bytes": 1024},
            HTTP_AUTHORIZATION="Bearer unique_storage_token",
            content_type="application/json"
        )
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["file_id"], storage_file_id)
        self.assertEqual(data["upload_url"], "https://s3.arna/presigned...")
        
        # Verify db state
        from django.db import connection
        connection.set_tenant(self.tenant)
        from storage.models import MediaReference
        ref = MediaReference.objects.get(id=data["reference_id"])
        self.assertEqual(ref.status, "upload_pending")
