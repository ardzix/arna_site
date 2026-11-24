"""Parse optional, deployment-owned Vercel proof settings; disabled by default."""
import json
from uuid import UUID

from core.domain_proof_policy import HOST, IDENTIFIER, receipt_key
from core.domain_proof_scope import PILOT_HOST, PILOT_ORGANIZATION, PILOT_TENANT


def _unique_pairs(pairs):
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError("duplicate field")
        fields[key] = value
    return fields


def _uuid(value):
    return isinstance(value, str) and str(UUID(value)) == value and UUID(value).int != 0


def read_vercel_proof_config(environment, django_secret):
    if environment.get("DOMAIN_VERCEL_PROOF_ENABLED") != "true":
        return False, "", "", {}, ""
    try:
        actor = environment.get("DOMAIN_VERCEL_PROOF_OPERATOR_ID", "")
        if not _uuid(actor):
            raise ValueError("immutable operator identity required")
        key = environment.get("DOMAIN_VERCEL_RECEIPT_KEY", "")
        token = environment.get("DOMAIN_VERCEL_API_TOKEN", "")
        receipt_key(key)
        if (key == django_secret or key == token or not token or
                len(token) > 4096 or any(c.isspace() for c in token)):
            raise ValueError("dedicated credentials required")
        raw = environment.get("DOMAIN_VERCEL_PROOF_BINDINGS", "")
        if len(raw) > 16384:
            raise ValueError("bindings size")
        bindings = json.loads(raw, object_pairs_hook=_unique_pairs)
        if not isinstance(bindings, dict) or set(bindings) != {PILOT_TENANT}:
            raise ValueError("bounded bindings required")
        seen_hosts = set()
        for tenant, binding in bindings.items():
            if (not _uuid(tenant) or not isinstance(binding, dict) or
                set(binding) != {"host", "organization_id", "project_id", "team_id"} or
                    not _uuid(binding["organization_id"])):
                raise ValueError("invalid binding identity")
            host = binding["host"]
            if host != PILOT_HOST or binding["organization_id"] != PILOT_ORGANIZATION:
                raise ValueError("unexpected pilot binding")
            if (not isinstance(host, str) or len(host) > 253 or not HOST.fullmatch(host) or
                    host in seen_hosts):
                raise ValueError("invalid or duplicate host")
            seen_hosts.add(host)
            for field, prefix in (("project_id", "prj_"), ("team_id", "team_")):
                value = binding[field]
                if not isinstance(value, str) or not value.startswith(prefix) or not IDENTIFIER.fullmatch(value):
                    raise ValueError("invalid provider identity")
        return True, key, token, bindings, actor
    except (ValueError, TypeError, RecursionError):
        raise RuntimeError("Vercel ownership proof configuration rejected; inspect managed settings privately.") from None
