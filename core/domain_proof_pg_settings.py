"""Only a disposable GitHub-runner PostgreSQL; no inherited database/credential settings."""
import os
if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("DOMAIN_PROOF_PG_BOUNDARY") != "disposable-github-job":
    raise RuntimeError("Disposable GitHub PostgreSQL boundary is required.")
from core.domain_proof_test_settings import *  # hermetic test settings, not deployment settings

DATABASES = {"default": {
    "ENGINE": "django_tenants.postgresql_backend",
    "NAME": "domain_proof_ci", "USER": "proof_ci", "PASSWORD": "synthetic-ci-only",
    "HOST": "127.0.0.1", "PORT": "55432", "CONN_MAX_AGE": 0,
    "OPTIONS": {"options": "-c statement_timeout=8000 -c lock_timeout=5000 -c application_name=domain-proof-ci"},
}}
