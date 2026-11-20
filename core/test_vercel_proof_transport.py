import unittest
from unittest.mock import MagicMock, patch
from core.domain_proof_policy import ProofError
from core.vercel_proof_transport import fetch_verified_evidence
from core.test_domain_proof_policy import BINDING, PROJECT, DOMAIN
import json


class TransportTests(unittest.TestCase):
    def response(self, value, status=200):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = status
        response.headers = {"Content-Type": "application/json"}
        response.iter_content.return_value = [json.dumps(value).encode()]
        return response

    def session(self, responses):
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.side_effect = responses
        return session

    def test_fixed_authenticated_get_only_no_proxy_or_redirect(self):
        session = self.session([self.response(PROJECT), self.response(DOMAIN)])
        with patch("core.vercel_proof_transport.requests.Session", return_value=session):
            evidence = fetch_verified_evidence(BINDING, "synthetic-token")
        self.assertEqual(evidence["verified"], True)
        self.assertFalse(session.trust_env)
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual([x.args[0] for x in session.get.call_args_list],
            ["https://api.vercel.com/v9/projects/prj_synthetic",
             "https://api.vercel.com/v9/projects/prj_synthetic/domains/example.test"])
        for call in session.get.call_args_list:
            self.assertFalse(call.kwargs["allow_redirects"])
            self.assertEqual(call.kwargs["params"], {"teamId": "team_synthetic"})
            self.assertEqual(call.kwargs["timeout"], (3, 5))
        session.post.assert_not_called()
        session.__exit__.assert_called_once()

    def test_redirect_and_provider_failure_rejected(self):
        for status in (301, 302, 401, 403, 404, 429, 500):
            session = self.session([self.response({}, status)])
            with self.subTest(status=status), patch("core.vercel_proof_transport.requests.Session", return_value=session), self.assertRaises(ProofError):
                fetch_verified_evidence(BINDING, "synthetic-token")

    def test_oversize_response_rejected(self):
        response = self.response({})
        response.iter_content.return_value = [b"x" * 65537]
        session = self.session([response])
        with patch("core.vercel_proof_transport.requests.Session", return_value=session), self.assertRaises(ProofError):
            fetch_verified_evidence(BINDING, "synthetic-token")

    def test_missing_token_does_not_connect(self):
        with patch("core.vercel_proof_transport.requests.Session") as session, self.assertRaises(ProofError):
            fetch_verified_evidence(BINDING, "")
        session.assert_not_called()
