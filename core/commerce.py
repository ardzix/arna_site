"""Module for core.commerce."""
import logging

from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class CommerceClientError(Exception):
    """CommerceClientError class."""
    pass


class CommerceClient:
    """CommerceClient class."""
    def __init__(self, bearer_token: str):
        self.base_url = getattr(settings, "ARNA_COMMERCE_BASE_URL", "https://product.arnatech.id/api/v1").rstrip("/")
        self.timeout = int(getattr(settings, "ARNA_COMMERCE_HTTP_TIMEOUT", 20))
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        resp = self.session.request(method=method, url=url, timeout=self.timeout, **kwargs)
        if resp.status_code >= 400:
            body = ""
            try:
                body = resp.text[:500]
            except Exception:
                pass
            raise CommerceClientError(f"{method} {path} failed ({resp.status_code}): {body}")
        if not resp.content:
            return {}
        return resp.json()

    @staticmethod
    def _results(payload: Any):
        if isinstance(payload, dict):
            if isinstance(payload.get("results"), list):
                return payload["results"]
            if isinstance(payload.get("data"), list):
                return payload["data"]
        if isinstance(payload, list):
            return payload
        return []

    def find_product_by_code(self, product_code: str):
        data = self._request("GET", "/products/", params={"search": product_code, "page_size": 100})
        for item in self._results(data):
            if item.get("code") == product_code:
                return item
        raise CommerceClientError(f"Product code not found: {product_code}")

    def find_plan_by_code(self, product_id: str, plan_code: str):
        data = self._request(
            "GET",
            "/plans/",
            params={"product": product_id, "search": plan_code, "is_active": "true", "page_size": 100},
        )
        for item in self._results(data):
            if item.get("code") == plan_code:
                return item
        raise CommerceClientError(f"Plan code not found: {plan_code}")

    def find_active_price(self, plan_id: str):
        data = self._request("GET", "/prices/", params={"plan": plan_id, "is_active": "true", "page_size": 100})
        rows = self._results(data)
        if not rows:
            raise CommerceClientError(f"No active price for plan: {plan_id}")
        for row in rows:
            if row.get("is_default") is True:
                return row
        return rows[0]

    def create_order(self, payload: dict):
        return self._request("POST", "/orders/", json=payload)

    def submit_order(self, order_id: str):
        return self._request("POST", f"/orders/{order_id}/submit/", json={})

    def create_order_payment(self, order_id: str, payload: dict):
        return self._request("POST", f"/orders/{order_id}/create-payment/", json=payload)

    def runtime_entitlements(self, organization_id: str, product_code: str, key_prefix: str):
        return self._request(
            "GET",
            "/entitlements/runtime/",
            params={
                "organization_id": organization_id,
                "product_code": product_code,
                "key_prefix": key_prefix,
            },
        )

    def process_payment_event(self, payload: dict):
        return self._request("POST", "/integrations/payment-events/process/", json=payload)

    def list_subscriptions(self, organization_id: str, product_id: str | None = None, status: str | None = None):
        """Return subscriptions filtered by organization and optional product/status."""
        params = {"organization_id": organization_id, "page_size": 100}
        if product_id:
            params["product"] = product_id
        if status:
            params["status"] = status
        data = self._request("GET", "/subscriptions/", params=params)
        return self._results(data)


def _catalog_cache_key(product_code: str, plan_code: str) -> str:
    """_catalog_cache_key helper."""
    return f"commerce:catalog:{product_code}:{plan_code}"


def resolve_catalog_ids(client: CommerceClient, product_code: str, plan_code: str):
    """resolve_catalog_ids helper."""
    key = _catalog_cache_key(product_code, plan_code)
    cached = cache.get(key)
    if cached:
        return cached

    product = client.find_product_by_code(product_code)
    plan = client.find_plan_by_code(product.get("id"), plan_code)
    price = client.find_active_price(plan.get("id"))
    resolved = {
        "product_id": product.get("id"),
        "plan_id": plan.get("id"),
        "price_id": price.get("id"),
    }
    cache.set(key, resolved, timeout=3600)
    return resolved


def bootstrap_free_plan_for_org(organization_id: str, bearer_token: str):
    """
    Best-effort free package bootstrap:
    create draft order then submit it so Commerce can materialize follow-up records.
    """
    product_code = getattr(settings, "ARNA_COMMERCE_PRODUCT_CODE", "arna-site")
    free_plan_code = getattr(settings, "ARNA_COMMERCE_FREE_PLAN_CODE", "arna-site-free")
    payment_method = getattr(settings, "ARNA_COMMERCE_FREE_PAYMENT_METHOD", "invoice")

    client = CommerceClient(bearer_token)
    ids = resolve_catalog_ids(client, product_code, free_plan_code)

    # Avoid creating an additional free subscription when this organization
    # already has an active package for the same product (e.g. premium).
    active_subscriptions = client.list_subscriptions(
        organization_id=organization_id,
        product_id=ids["product_id"],
        status="active",
    )
    if active_subscriptions:
        logger.info(
            "Skip free bootstrap for org=%s because active subscription already exists (count=%s).",
            organization_id,
            len(active_subscriptions),
        )
        return {"skipped": True, "reason": "active_subscription_exists", "active_count": len(active_subscriptions)}

    order = client.create_order(
        {
            "organization_id": organization_id,
            "product": ids["product_id"],
            "plan": ids["plan_id"],
            "price": ids["price_id"],
            "payment_method": payment_method,
            "notes": "ArnaSite automatic free bootstrap",
        }
    )
    submit = client.submit_order(order["id"])
    invoice_number = ""
    if isinstance(submit, dict):
        invoice_number = ((submit.get("invoice") or {}).get("invoice_number") or "")
    activation = {}
    if invoice_number:
        activation = client.process_payment_event(
            {
                "webhook_data": {
                    "id": f"internal-free-{order['id']}",
                    "external_id": invoice_number,
                    "status": "PAID",
                },
                "metadata": {
                    "xendit_event": "invoice.paid",
                    "source": "arna_site_internal_bootstrap",
                },
            }
        )
    return {"order": order, "submit": submit, "activation": activation}
