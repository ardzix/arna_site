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
        domain = SimpleNamespace(tenant=tenant, crm_tenant=None, role=Domain.ROLE_FRONTEND_DEFAULT, ownership_proof_required=False)
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
        domain = SimpleNamespace(tenant=SimpleNamespace(sso_organization_id="not-an-org", public_id=68), crm_tenant=None, role=Domain.ROLE_FRONTEND_DEFAULT, ownership_proof_required=False)
        response, _ = self.call("customer.example.com", domain)
        self.assertEqual(response.status_code, 503)

    def test_crm_destination_keeps_website_owner_and_routes_only_crm(self):
        owner = SimpleNamespace(sso_organization_id=uuid4(), public_id=uuid4())
        target = SimpleNamespace(sso_organization_id=owner.sso_organization_id, public_id=uuid4(), is_active=True)
        domain = SimpleNamespace(tenant=owner, crm_tenant=target, role=Domain.ROLE_FRONTEND_DEFAULT, ownership_proof_required=False)
        response, _ = self.call("customer.example.com", domain)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["tenant_id"], str(target.public_id))
        self.assertEqual(response.data["organization_id"], str(owner.sso_organization_id))
        self.assertIs(domain.tenant, owner)

    def test_inactive_cross_org_or_malformed_destination_fails_closed(self):
        owner = SimpleNamespace(sso_organization_id=uuid4(), public_id=uuid4())
        for active, org, identity in [(False, owner.sso_organization_id, uuid4()),
                                      (True, uuid4(), uuid4()),
                                      (True, "invalid", uuid4()),
                                      (True, owner.sso_organization_id, "invalid")]:
            with self.subTest(active=active, org=org, identity=identity):
                target = SimpleNamespace(is_active=active, sso_organization_id=org, public_id=identity)
                response, _ = self.call("customer.example.com", SimpleNamespace(tenant=owner, crm_tenant=target, role=Domain.ROLE_FRONTEND_DEFAULT, ownership_proof_required=False))
                self.assertEqual(response.status_code, 503)

    def test_crm_destination_cannot_bypass_required_ownership_proof(self):
        owner = SimpleNamespace(sso_organization_id=uuid4(), public_id=uuid4())
        target = SimpleNamespace(sso_organization_id=owner.sso_organization_id, public_id=uuid4(), is_active=True)
        host = "customer.example.com"
        domain = SimpleNamespace(
            tenant=owner, crm_tenant=target, role=Domain.ROLE_FRONTEND_CUSTOM,
            ownership_proof_required=True, status=Domain.STATUS_ACTIVE, verified_at=True,
            verification_method="vercel-api-v1", domain=host, pk=10,
        )
        with patch("core.domain_proof_admission.DomainOwnershipAudit.objects") as audit:
            audit.filter.return_value.exists.return_value = False
            self.assertEqual(self.call(host, domain)[0].status_code, 404)
            audit.filter.return_value.exists.return_value = True
            response, _ = self.call(host, domain)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["tenant_id"], str(target.public_id))
            audit.filter.assert_called_with(
                domain_id=domain.pk, hostname=host, tenant_public_id=owner.public_id,
                organization_id=owner.sso_organization_id, provider="vercel-api-v1",
            )


class WebsiteCRMDestinationValidationTest(SimpleTestCase):
    def test_domain_model_rejects_inactive_or_other_org_destination(self):
        from django.core.exceptions import ValidationError
        from core.models import Tenant

        org = str(uuid4())
        owner = Tenant(pk=1, sso_organization_id=org)
        for active, target_org in [(False, org), (True, str(uuid4())), (True, "invalid")]:
            domain = Domain(tenant=owner, crm_tenant=Tenant(pk=2, sso_organization_id=target_org, is_active=active))
            with self.assertRaises(ValidationError):
                domain.clean()
        Domain(tenant=owner, crm_tenant=Tenant(pk=2, sso_organization_id=org, is_active=True)).clean()
        Domain(tenant=owner).clean()
