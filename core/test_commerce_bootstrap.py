from unittest.mock import patch, Mock
from django.test import SimpleTestCase, override_settings
from core.commerce import CommerceClient, CommerceClientError, bootstrap_free_plan_for_org


class FreeBootstrapClientTests(SimpleTestCase):
    @override_settings(ARNA_COMMERCE_PRODUCT_CODE="site", ARNA_COMMERCE_FREE_PLAN_CODE="free")
    def test_registration_uses_owned_zero_checkout_command_and_no_fake_webhook(self):
        expected = {"order": {"id": "order", "status": "paid"}, "subscription": {"status": "active"}, "skipped": False}
        with patch("core.commerce.resolve_catalog_ids", return_value={"product_id": "p", "plan_id": "plan", "price_id": "price"}), patch.object(CommerceClient, "_request", return_value=expected) as request:
            result = bootstrap_free_plan_for_org("own-org", "synthetic-human-token")
        self.assertEqual(result, expected)
        request.assert_called_once_with("POST", "/orders/bootstrap-free/", json={
            "organization_id": "own-org", "product": "p", "plan": "plan", "price": "price", "quantity": 1, "payment_method": "invoice"})

    def test_repeated_registration_accepts_existing_active_package(self):
        reply = {"skipped": True, "reason": "active_subscription_exists"}
        with patch("core.commerce.resolve_catalog_ids", return_value={"product_id": "p", "plan_id": "plan", "price_id": "price"}), patch.object(CommerceClient, "bootstrap_free_order", return_value=reply):
            self.assertEqual(bootstrap_free_plan_for_org("own-org", "synthetic"), reply)

    def test_zero_checkout_failure_is_reported_without_payment_event_fallback(self):
        with patch("core.commerce.resolve_catalog_ids", return_value={"product_id": "p", "plan_id": "plan", "price_id": "price"}), patch.object(CommerceClient, "bootstrap_free_order", side_effect=CommerceClientError("denied")), patch.object(CommerceClient, "process_payment_event") as event:
            with self.assertRaises(CommerceClientError):
                bootstrap_free_plan_for_org("own-org", "synthetic")
            event.assert_not_called()
