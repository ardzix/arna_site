from unittest.mock import Mock, patch
from django.test import RequestFactory, SimpleTestCase
from core.health import ReleaseHealthMiddleware


class ReleaseHealthTests(SimpleTestCase):
    def test_liveness_does_not_depend_on_database_or_tenant_lookup(self):
        next_handler = Mock()
        with patch('core.health.connection') as database:
            database.cursor.side_effect = RuntimeError('unavailable')
            self.assertEqual(ReleaseHealthMiddleware(next_handler)(RequestFactory().get('/health/live')).status_code, 200)
        next_handler.assert_not_called()

    def test_database_failure_returns_sanitized_readiness_error(self):
        with patch('core.health.connection') as database:
            database.cursor.side_effect = RuntimeError('private connection details')
            response = ReleaseHealthMiddleware(Mock())(RequestFactory().get('/health/ready'))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'private', response.content)

    def test_non_health_request_keeps_normal_tenant_auth_pipeline(self):
        next_handler = Mock(return_value='normal-response')
        request = RequestFactory().get('/tenants/')
        self.assertEqual(ReleaseHealthMiddleware(next_handler)(request), 'normal-response')
        next_handler.assert_called_once_with(request)
