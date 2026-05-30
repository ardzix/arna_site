from django.conf import settings

from core.commerce import CommerceClient, CommerceClientError


class LimitError(Exception):
    pass


def _to_int(value, default=0):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def fetch_runtime_entitlements(org_id: str, bearer_token: str):
    product_code = getattr(settings, "ARNA_COMMERCE_PRODUCT_CODE", "arna-site")
    key_prefix = getattr(settings, "ARNA_COMMERCE_ENTITLEMENT_KEY_PREFIX", "arnasite.")
    payload = CommerceClient(bearer_token).runtime_entitlements(
        organization_id=org_id,
        product_code=product_code,
        key_prefix=key_prefix,
    )
    return payload.get("entitlements", {}) if isinstance(payload, dict) else {}


def assert_max_websites(entitlements: dict, current_count: int):
    limit = _to_int(entitlements.get("arnasite.max_websites"), 1)
    if limit > 0 and current_count >= limit:
        raise LimitError(f"Website limit reached ({current_count}/{limit}). Upgrade your package.")


def assert_max_templates(entitlements: dict, current_count: int):
    limit = _to_int(entitlements.get("arnasite.max_templates"), 3)
    if limit > 0 and current_count >= limit:
        raise LimitError(f"Template limit reached ({current_count}/{limit}). Upgrade your package.")


def assert_max_pages_per_template(entitlements: dict, current_count: int):
    limit = _to_int(entitlements.get("arnasite.max_pages_per_template"), 1)
    if limit > 0 and current_count >= limit:
        raise LimitError(f"Page limit reached ({current_count}/{limit}) for this website.")


def assert_custom_domain_enabled(entitlements: dict):
    raw = str(entitlements.get("arnasite.custom_domain.enabled", "")).strip().lower()
    if raw not in {"1", "true", "yes"}:
        raise LimitError("Custom domain is not enabled in your current package.")


def assert_ai_monthly_calls(entitlements: dict, month_usage: int):
    limit = _to_int(entitlements.get("arnasite.ai_generator.monthly_calls"), 20)
    if limit > 0 and month_usage >= limit:
        raise LimitError(f"AI monthly quota reached ({month_usage}/{limit}).")
