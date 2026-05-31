"""Module for core.limits."""
from django.conf import settings


from core.commerce import CommerceClient, CommerceClientError


class LimitError(Exception):
    """Raised when an organization exceeds an entitlement-enforced limit."""

    pass


def _to_int(value, default=0):
    """Safely coerce string-like entitlement values to integers."""

    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def fetch_runtime_entitlements(org_id: str, bearer_token: str):
    """Fetch runtime entitlement key/value pairs for an organization from Commerce."""

    product_code = getattr(settings, "ARNA_COMMERCE_PRODUCT_CODE", "arna-site")
    key_prefix = getattr(settings, "ARNA_COMMERCE_ENTITLEMENT_KEY_PREFIX", "arnasite.")
    payload = CommerceClient(bearer_token).runtime_entitlements(
        organization_id=org_id,
        product_code=product_code,
        key_prefix=key_prefix,
    )
    return payload.get("entitlements", {}) if isinstance(payload, dict) else {}


def assert_max_websites(entitlements: dict, current_count: int):
    """Validate active website/tenant count against `arnasite.max_websites`."""

    limit = _to_int(entitlements.get("arnasite.max_websites"), 1)
    if limit > 0 and current_count >= limit:
        raise LimitError(f"Website limit reached ({current_count}/{limit}). Upgrade your package.")


def assert_max_templates(entitlements: dict, current_count: int):
    """Validate template count against `arnasite.max_templates`."""

    limit = _to_int(entitlements.get("arnasite.max_templates"), 3)
    if limit > 0 and current_count >= limit:
        raise LimitError(f"Template limit reached ({current_count}/{limit}). Upgrade your package.")


def assert_max_pages_per_template(entitlements: dict, current_count: int):
    """Validate page count within one tenant site against `arnasite.max_pages_per_template`."""

    limit = _to_int(entitlements.get("arnasite.max_pages_per_template"), 1)
    if limit > 0 and current_count >= limit:
        raise LimitError(f"Page limit reached ({current_count}/{limit}) for this website.")


def assert_custom_domain_enabled(entitlements: dict):
    """Ensure custom-domain feature flag is enabled for the current package."""

    raw = str(entitlements.get("arnasite.custom_domain.enabled", "")).strip().lower()
    if raw not in {"1", "true", "yes"}:
        raise LimitError("Custom domain is not enabled in your current package.")


def assert_ai_monthly_calls(entitlements: dict, month_usage: int):
    """Validate monthly AI usage against `arnasite.ai_generator.monthly_calls`."""

    limit = _to_int(entitlements.get("arnasite.ai_generator.monthly_calls"), 20)
    if limit > 0 and month_usage >= limit:
        raise LimitError(f"AI monthly quota reached ({month_usage}/{limit}).")


def _to_bool(value, default=False):
    """Safely coerce string-like entitlement values to booleans."""

    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_premium_like(entitlements: dict):
    """
    Infer premium/enterprise capability from runtime entitlements.

    Priority:
    1) Explicit key `arnasite.premium.enabled` if present.
    2) Custom domain enabled (premium feature).
    3) `max_websites > 1` as fallback signal.
    """

    if "arnasite.premium.enabled" in entitlements:
        return _to_bool(entitlements.get("arnasite.premium.enabled"), False)
    custom_domain_enabled = _to_bool(entitlements.get("arnasite.custom_domain.enabled"), False)
    if custom_domain_enabled:
        return True
    return _to_int(entitlements.get("arnasite.max_websites"), 1) > 1


def assert_template_generation_enabled(entitlements: dict):
    """
    Ensure AI template generation is allowed for current package.

    Explicit override key:
    - `arnasite.ai.template_generation.enabled`
    Fallback behavior:
    - allow only premium-like packages.
    """

    if "arnasite.ai.template_generation.enabled" in entitlements:
        enabled = _to_bool(entitlements.get("arnasite.ai.template_generation.enabled"), False)
    else:
        enabled = _is_premium_like(entitlements)
    if not enabled:
        raise LimitError(
            "Your free package doesn't include template generation, please use available template or upgrade to premium."
        )


def assert_template_manual_creation_enabled(entitlements: dict):
    """
    Ensure manual template creation is allowed for current package.

    Explicit override key:
    - `arnasite.template.manual_creation.enabled`
    Fallback behavior:
    - allow only premium-like packages.
    """

    if "arnasite.template.manual_creation.enabled" in entitlements:
        enabled = _to_bool(entitlements.get("arnasite.template.manual_creation.enabled"), False)
    else:
        enabled = _is_premium_like(entitlements)
    if not enabled:
        raise LimitError(
            "Your free package doesn't include template creation, please use available template or upgrade to premium."
        )
