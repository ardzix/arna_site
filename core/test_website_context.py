from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from core.models import Domain
from core.website_context import PublicWebsiteContextView


class WebsiteContextTest(SimpleTestCase):
    def call(self, host, domain):
        with patch("core.website_context.schema_context", return_value=nullcontext()), patch(
            "core.website_context.Domain.objects"
        ) as manager:
            manager.select_related.return_value.filter.return_value.first.return_value = domain
            response = PublicWebsiteContextView.as_view()(APIRequestFactory().get("/", {"host": host}))
            return response, manager

    def test_aliases_keep_the_same_public_uuid_identity(self):
        tenant = SimpleNamespace(sso_organization_id=uuid4(), public_id=uuid4())
        domain = SimpleNamespace(tenant=tenant)
        for host in ["customer.bisnisnaikkelas.com", "customer-alias.example.com"]:
            response, manager = self.call(host, domain)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["organization_id"], str(tenant.sso_organization_id))
            self.assertEqual(response.data["tenant_id"], str(tenant.public_id))
            manager.select_related.return_value.filter.assert_called_once_with(
                domain=host, role__in=[Domain.ROLE_FRONTEND_DEFAULT, Domain.ROLE_FRONTEND_CUSTOM],
                status=Domain.STATUS_ACTIVE, verified_at__isnull=False, tenant__is_active=True,
            )
            self.assertEqual(set(response.data), {"host", "origin", "organization_id", "tenant_id"})

    def test_unregistered_inactive_or_unverified_domain_is_not_a_context(self):
        response, _ = self.call("unknown.example.com", None)
        self.assertEqual(response.status_code, 404)

    def test_urls_ports_uppercase_and_missing_hosts_are_rejected(self):
        for host in ["", "https://customer.example.com", "localhost", "customer.example.com:443", "Customer.example.com", "customer.example.com/"]:
            response, manager = self.call(host, None)
            self.assertEqual(response.status_code, 400)
            manager.select_related.assert_not_called()

    def test_legacy_numeric_or_invalid_identity_fails_closed(self):
        domain = SimpleNamespace(tenant=SimpleNamespace(sso_organization_id="not-an-org", public_id=68))
        response, _ = self.call("customer.example.com", domain)
        self.assertEqual(response.status_code, 503)
