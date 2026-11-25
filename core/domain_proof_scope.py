"""Pilot scope is code-pinned. Changing it requires review, not a request parameter."""
PILOT_HOST = "arnatech.id"
PILOT_DOMAIN_ID = 174
PILOT_TENANT = "10996862-26be-4c7a-8a05-acb814f77975"
PILOT_ORGANIZATION = "25c1bf82-5eac-4507-a5d7-b1e271fdbb9f"


def is_pilot_host(value):
    return isinstance(value, str) and value.strip().rstrip(".").lower() == PILOT_HOST


def is_exact_pilot_domain(domain):
    return (domain.pk == PILOT_DOMAIN_ID and domain.domain == PILOT_HOST
            and domain.role == "frontend_custom" and domain.tenant.is_active
            and str(domain.tenant.public_id) == PILOT_TENANT
            and str(domain.tenant.sso_organization_id) == PILOT_ORGANIZATION)
