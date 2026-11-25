"""Bounded runner for the dedicated, disposable GitHub job database only."""
import json
import os
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("DOMAIN_PROOF_PG_BOUNDARY") != "disposable-github-job":
    raise SystemExit("Refusing non-disposable execution.")
os.environ["DJANGO_SETTINGS_MODULE"] = "core.domain_proof_pg_settings"
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

connection.set_schema_to_public()
with connection.cursor() as cursor:
    cursor.execute("SELECT current_database(), current_user, current_setting('server_version_num')::int, inet_server_addr()::text")
    database, user, version, address = cursor.fetchone()
    assert (database, user, version) == ("domain_proof_ci", "proof_ci", 160013)
    cursor.execute("SELECT datname FROM pg_database WHERE NOT datistemplate")
    assert {row[0] for row in cursor.fetchall()} == {"postgres", "domain_proof_ci"}
    cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
    assert cursor.fetchone()[0] == 0, "Database is not fresh."
print(json.dumps({"boundary": "disposable GitHub-hosted job / owned PostgreSQL container / tmpfs data",
                  "server_version_num": version, "database": database, "provider": "synthetic",
                  "auth": "synthetic managed HTTPS operator; no external authentication"}), flush=True)

BASE = ("core", "0008_domain_crm_tenant")
HEAD = ("core", "0009_domain_ownership_proof")
executor = MigrationExecutor(connection)
executor.migrate([BASE])
old = executor.loader.project_state([BASE]).apps
OldTenant, OldDomain = old.get_model("core", "Tenant"), old.get_model("core", "Domain")
tenant = OldTenant.objects.create(schema_name="public", name="Synthetic migration fixture",
                                  slug="migration-" + uuid.uuid4().hex, sso_organization_id=str(uuid.uuid4()))
crm = OldTenant.objects.create(schema_name="public", name="Synthetic CRM destination",
                               slug="migration-" + uuid.uuid4().hex,
                               sso_organization_id=tenant.sso_organization_id)
legacy = OldDomain.objects.create(tenant=tenant, crm_tenant=crm, domain="legacy.example.test",
                                  role="frontend_custom", status="active",
                                  verified_at=timezone.now(), is_primary=False)
pending = OldDomain.objects.create(tenant=tenant, domain="pending.example.test", role="frontend_custom",
                                   status="pending_verification", verification_token=uuid.uuid4().hex,
                                   verification_method="txt", is_primary=False)
default = OldDomain.objects.create(tenant=tenant, domain="default.example.test", role="frontend_default",
                                   status="active", verified_at=timezone.now(), is_primary=False)
preserved = {item.pk: (item.domain, item.status, item.verified_at, item.verification_token, item.crm_tenant_id)
             for item in (legacy, pending, default)}
executor = MigrationExecutor(connection)
executor.migrate([HEAD])
from core.models import Domain, DomainOwnershipAudit
for pk, expected in preserved.items():
    item = Domain.objects.get(pk=pk)
    assert (item.domain, item.status, item.verified_at, item.verification_token, item.crm_tenant_id) == expected
assert Domain.objects.get(pk=legacy.pk).crm_tenant_id == crm.pk
print(json.dumps({"migration_forward": "passed", "unrelated_pending_row_unchanged": True,
                  "existing_active_legacy_preserved": True}), flush=True)

suite = unittest.defaultTestLoader.loadTestsFromName("core.test_domain_proof_postgres")
result = unittest.TextTestRunner(verbosity=2).run(suite)
print(json.dumps({"real_postgres_tests": result.testsRun, "failures": len(result.failures),
                  "errors": len(result.errors), "skipped": len(result.skipped)}), flush=True)
if not result.wasSuccessful():
    raise SystemExit(1)

# Destructive rollback is demonstrated ONLY in this disposable DB.
# It is not the production rollback recommendation: audit/history is dropped by reverse DDL.
connection.set_schema_to_public()
before_domains = dict(Domain.objects.values_list("pk", "domain"))
before_audits = DomainOwnershipAudit.objects.count()
assert before_audits > 0
MigrationExecutor(connection).migrate([BASE])
old = MigrationExecutor(connection).loader.project_state([BASE]).apps
OldDomain = old.get_model("core", "Domain")
assert dict(OldDomain.objects.values_list("pk", "domain")) == before_domains
for pk, expected in preserved.items():
    item = OldDomain.objects.get(pk=pk)
    assert (item.domain, item.status, item.verified_at, item.verification_token, item.crm_tenant_id) == expected
with connection.cursor() as cursor:
    cursor.execute("SELECT to_regclass('public.core_domainownershipaudit')")
    assert cursor.fetchone()[0] is None
print(json.dumps({"migration_reverse_DDL": "passed", "business_domain_rows_preserved": True,
                  "audit_records_dropped": before_audits,
                  "production_safe_schema_rollback": False,
                  "recommended_rollback": "disable feature/keep forward schema and audit; website remains off"}), flush=True)
MigrationExecutor(connection).migrate([HEAD])
assert DomainOwnershipAudit.objects.count() == 0
assert Domain.objects.get(pk=legacy.pk).crm_tenant_id == crm.pk
print(json.dumps({"migration_reapply": "passed", "reverse_reapply_restores_audit": False,
                  "warning": "Reverse DDL loses proof history. Never use as production rollback without separate reviewed restoration."}), flush=True)
connection.close()
