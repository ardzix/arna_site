"""Private, purpose-separated ArnaSite receipts. No network/DB."""
import base64
import hashlib
import hmac
import json
import re
import time
from uuid import UUID

TTL = 120
SALT = b"arnasite:domain-proof:https-receipt:v1:"
CHALLENGE_SALT = b"arnasite:domain-proof:https-challenge:v1:"
CHALLENGE_TTL = 900
HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{4,100}")


class ProofError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def validate_snapshot(value):
    expected = {"domain_id", "host", "tenant_id", "organization_id", "challenge_hash", "method", "actor_id"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ProofError("invalid_snapshot")
    if type(value["domain_id"]) is not int or value["domain_id"] < 1:
        raise ProofError("invalid_domain")
    host = value["host"]
    if not isinstance(host, str) or len(host) > 253 or not HOST.fullmatch(host):
        raise ProofError("invalid_host")
    for key in ("tenant_id", "organization_id", "actor_id"):
        try:
            if str(UUID(value[key])) != value[key]:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ProofError("invalid_identity") from None
    if not isinstance(value["challenge_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["challenge_hash"]):
        raise ProofError("invalid_challenge")
    if not isinstance(value["method"], str) or len(value["method"]) > 32:
        raise ProofError("invalid_method")
    return value



def receipt_key(key):
    if not isinstance(key, str) or len(key.encode("utf-8")) < 32:
        raise ProofError("receipt_key_unconfigured")
    return key.encode("utf-8")


def issue_receipt(snapshot, binding, evidence, key, now=None, *, ttl=TTL, salt=SALT):
    validate_snapshot(snapshot)
    now = int(time.time()) if now is None else now
    claims = {"v": 1, "snapshot": snapshot, "binding": binding, "evidence_hash": digest(canonical(evidence)),
              "iat": now, "exp": now + ttl}
    payload = base64.urlsafe_b64encode(canonical(claims).encode()).rstrip(b"=")
    signature = hmac.new(receipt_key(key), salt + payload, hashlib.sha256).hexdigest()
    return payload.decode() + "." + signature


def read_receipt(receipt, key, now=None, *, ttl=TTL, salt=SALT):
    if not isinstance(receipt, str) or len(receipt) > 4096:
        raise ProofError("invalid_receipt")
    try:
        payload, signature = receipt.split(".")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", payload) or not re.fullmatch(r"[0-9a-f]{64}", signature):
            raise ValueError()
        expected = hmac.new(receipt_key(key), salt + payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if set(claims) != {"v", "snapshot", "binding", "evidence_hash", "iat", "exp"} or claims["v"] != 1:
            raise ValueError()
        validate_snapshot(claims["snapshot"])
        now = int(time.time()) if now is None else now
        if type(claims["iat"]) is not int or type(claims["exp"]) is not int:
            raise ValueError()
        if claims["exp"] != claims["iat"] + ttl or not claims["iat"] <= now < claims["exp"]:
            raise ValueError()
        if not isinstance(claims["evidence_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", claims["evidence_hash"]):
            raise ValueError()
        return claims
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ProofError("invalid_or_expired_receipt") from None


def require_same_state(claims, snapshot, binding, evidence):
    validate_snapshot(snapshot)
    if claims["snapshot"] != snapshot or claims["binding"] != binding:
        raise ProofError("ownership_state_changed")
    if claims["evidence_hash"] != digest(canonical(evidence)):
        raise ProofError("provider_evidence_changed")
