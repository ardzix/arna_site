"""Synthetic public DNS/TLS pin and HTTP body admission, without sockets."""
import socket
import ssl
import unittest
from unittest.mock import Mock, patch

from core.domain_proof_policy import ProofError
from core.https_proof_transport import HOST, PATH, PinnedHTTPSConnection, fetch_https_evidence, public_endpoint

IP = "93.184.216.34"
ENDPOINT = (socket.AF_INET, (IP, 443))
VALUE = "arnatech-bnk-https-v1 " + "1" * 64 + " 1795540900"


def row(address, port=443):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port, 0, 0) if family == socket.AF_INET6 else (address, port))


class TransportTests(unittest.TestCase):
    def test_dns_rejects_nonpublic_mixed_address_and_pins_public_port(self):
        with patch("core.https_proof_transport.socket.getaddrinfo", return_value=[row(IP)]) as lookup:
            self.assertEqual(public_endpoint(), ENDPOINT)
            lookup.assert_called_once_with(HOST, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        for address in ("127.0.0.1", "10.0.0.5", "169.254.169.254", "224.0.0.1", "::1", "::ffff:127.0.0.1",
                        "64:ff9b::127.0.0.1", "2002:7f00:1::"):
            with self.subTest(address=address), patch("core.https_proof_transport.socket.getaddrinfo",
                                                      return_value=[row(IP), row(address)]), self.assertRaises(ProofError):
                public_endpoint()

    def test_numeric_connect_reuses_exact_address_and_keeps_canonical_sni(self):
        tls = Mock()
        with patch("core.https_proof_transport.socket.socket") as sockets, patch(
            "core.https_proof_transport.socket.getaddrinfo"
        ) as lookup:
            c = PinnedHTTPSConnection(ENDPOINT, tls)
            c.connect()
            sockets.return_value.connect.assert_called_once_with((IP, 443))
            tls.wrap_socket.assert_called_once_with(sockets.return_value, server_hostname=HOST)
            lookup.assert_not_called()

    def test_only_fixed_authenticated_get_accepts_small_exact_uncached_text(self):
        default = {"Content-Type": "text/plain; charset=utf-8", "Cache-Control": "private, no-store"}
        for status, headers, body, success in [
            (200, default, VALUE.encode("ascii"), True),
            (302, {**default, "Location": "http://127.0.0.1/"}, b"", False),
            (200, {**default, "Cache-Control": "max-age=300"}, VALUE.encode("ascii"), False),
            (200, {**default, "Content-Encoding": "gzip"}, VALUE.encode("ascii"), False),
            (200, {**default, "Content-Type": "text/html"}, VALUE.encode("ascii"), False),
            (200, default, b"x" * 129, False),
            (200, default, VALUE.encode("ascii") + b"\n", False),
        ]:
            with self.subTest(status=status, headers=headers, success=success), patch(
                "core.https_proof_transport.public_endpoint", return_value=ENDPOINT
            ), patch("core.https_proof_transport.PinnedHTTPSConnection") as co:
                connection = co.return_value
                response = connection.getresponse.return_value
                response.status = status
                response.getheader.side_effect = headers.get
                response.read.return_value = body
                if success:
                    self.assertEqual(fetch_https_evidence(VALUE)["provider"], "https-origin-v1")
                else:
                    with self.assertRaises(ProofError):
                        fetch_https_evidence(VALUE)
                conn_args = co.call_args.args
                self.assertIs(conn_args[1].verify_mode, ssl.CERT_REQUIRED)
                self.assertTrue(conn_args[1].check_hostname)
                self.assertEqual(connection.request.call_count, 1)
                self.assertEqual(connection.request.call_args.args, ("GET", PATH))
                connection.close.assert_called_once()
