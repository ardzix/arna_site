"""Authenticated, GET-only fixed Vercel control-plane adapter. Never fetch tenant hosts."""
import requests
import time
from core.domain_proof_policy import ProofError, verified_evidence

MAX_RESPONSE = 65536


def fetch_verified_evidence(binding, api_token):
    if not isinstance(api_token, str) or not api_token or any(c in api_token for c in "\r\n"):
        raise ProofError("provider_unconfigured")
    try:
        with requests.Session() as session:
            session.trust_env = False
            headers = {"Authorization": "Bearer " + api_token, "Accept": "application/json"}
            base = "https://api.vercel.com/v9/projects/" + binding["project_id"]
            values = []
            deadline = time.monotonic() + 10
            for url in (base, base + "/domains/" + binding["host"]):
                with session.get(url, params={"teamId": binding["team_id"]}, headers=headers,
                                 timeout=(3, 5), allow_redirects=False, stream=True) as response:
                    if response.status_code != 200 or not response.headers.get("Content-Type", "").lower().startswith("application/json"):
                        raise ProofError("provider_unavailable")
                    data = bytearray()
                    for chunk in response.iter_content(chunk_size=4096):
                        if time.monotonic() > deadline:
                            raise ProofError("provider_deadline")
                        data.extend(chunk)
                        if len(data) > MAX_RESPONSE:
                            raise ProofError("provider_response_limit")
                    import json
                    values.append(json.loads(data))
            return verified_evidence(values[0], values[1], binding)
    except (requests.RequestException, ValueError, TypeError, KeyError):
        # Exception strings can contain request/response details; never expose them.
        raise ProofError("provider_verification_failed") from None
