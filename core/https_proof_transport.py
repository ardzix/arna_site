"""Fixed public HTTPS origin proof. No user URL, redirects, proxy or provider token."""
import http.client
import ipaddress
import socket
import ssl
import time
from hmac import compare_digest

from core.domain_proof_policy import ProofError, digest

HOST = "arnatech.id"
PATH = "/.well-known/arnatech-bnk-verification/"
MAX_RESPONSE = 128
NETWORK_TIMEOUT = 6


def public_endpoint():
    # A single DNS lookup; only connect to the vetted numeric address. Runtime
    # must also apply its bounded operator deadline to DNS itself.
    rows = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    candidates = []
    for family, kind, proto, _, address in rows:
        if family not in (socket.AF_INET, socket.AF_INET6) or kind != socket.SOCK_STREAM:
            raise ProofError("nonpublic_proof_address")
        ip = ipaddress.ip_address(address[0])
        if (address[1] != 443 or not ip.is_global or ip.is_multicast or ip.is_reserved or
            (isinstance(ip, ipaddress.IPv6Address) and any(ip in net for net in
                 (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48")))) or
            (isinstance(ip, ipaddress.IPv6Address) and
             (ip.ipv4_mapped or ip.sixtofour or ip.teredo or address[3]))):
            raise ProofError("nonpublic_proof_address")
        candidates.append((family, address))
    if not candidates:
        raise ProofError("no_proof_address")
    return candidates[0]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, endpoint, context):
        self.endpoint, self.verified_context = endpoint, context
        super().__init__(HOST, 443, timeout=NETWORK_TIMEOUT, context=context)

    def connect(self):
        # Keep numeric route fixed while authenticating the DNS name with TLS.
        family, address = self.endpoint
        raw = socket.socket(family, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        try:
            raw.settimeout(self.timeout)
            raw.connect(address)
            self.sock = self.verified_context.wrap_socket(raw, server_hostname=HOST)
        except BaseException:
            raw.close()
            raise


def fetch_https_evidence(expected):
    deadline = time.monotonic() + NETWORK_TIMEOUT + 2
    try:
        endpoint = public_endpoint()
        if time.monotonic() >= deadline:
            raise ProofError("proof_deadline")
        tls = ssl.create_default_context()
        with_connection = PinnedHTTPSConnection(endpoint, tls)
        try:
            with_connection.request("GET", PATH, headers={
                "Accept": "text/plain", "Accept-Encoding": "identity",
                "Cache-Control": "no-cache", "Connection": "close",
            })
            response = with_connection.getresponse()
            content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
            cache_control = {value.strip().lower() for value in (response.getheader("Cache-Control") or "").split(",")}
            enc = (response.getheader("Content-Encoding") or "identity").lower()
            if response.status != 200 or content_type != "text/plain" or enc != "identity" or "no-store" not in cache_control:
                raise ProofError("proof_response_rejected")
            body = response.read(MAX_RESPONSE+1)
            if time.monotonic() >= deadline:
                raise ProofError("proof_deadline")
            if len(body) > MAX_RESPONSE or not compare_digest(body, expected.encode("ascii")):
                raise ProofError("proof_challenge_mismatch")
            return {"provider": "https-origin-v1", "host": HOST, "path": PATH,
                    "challenge_hash": digest(expected), "tls_verified": True}
        finally:
            with_connection.close()
    except ProofError:
        raise
    except (OSError, ValueError, TypeError, IndexError, http.client.HTTPException):
        raise ProofError("proof_transport_failed") from None
