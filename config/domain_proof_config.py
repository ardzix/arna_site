"""Disabled-by-default HTTPS proof settings. No cloud access token is used."""
from uuid import UUID

from core.domain_proof_policy import receipt_key


def read_https_proof_config(environment, django_secret):
    if environment.get("DOMAIN_HTTPS_PROOF_ENABLED") != "true":
        return False, "", ""
    try:
        actor = environment.get("DOMAIN_HTTPS_PROOF_OPERATOR_ID", "")
        if str(UUID(actor)) != actor or UUID(actor).int == 0:
            raise ValueError()
        key = environment.get("DOMAIN_HTTPS_RECEIPT_KEY", "")
        receipt_key(key)
        if key == django_secret:
            raise ValueError()
        return True, key, actor
    except (ValueError, TypeError, AttributeError):
        raise RuntimeError("HTTPS ownership proof configuration rejected; inspect managed settings privately.") from None
