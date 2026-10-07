"""Backfill legacy CMS ownership to Tenant.public_id across registered schemas."""

import hashlib
import json
import os
from collections import defaultdict
from contextlib import nullcontext
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django_tenants.utils import schema_context

from core.models import Tenant
from sites.models import Page, Section, ContentBlock, ListItem
from sites.tenant_identity_repair import plan_schema_repair


MODELS = {"pages": Page, "sections": Section, "blocks": ContentBlock, "items": ListItem}


def snapshot():
    return {name: list(model.objects.order_by("id").values()) for name, model in MODELS.items()}


class Command(BaseCommand):
    help = "Audit/backfill integer-as-UUID Page/Section owners to public UUIDs. Dry run by default."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--backup-path", help="Exclusive 0600 JSON snapshot file; required with --apply.")

    def handle(self, *args, **options):
        if options["apply"] and not options["backup_path"]:
            raise CommandError("--apply requires --backup-path")
        try:
            self.repair(options)
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc

    def repair(self, options):
        apply = options["apply"]
        with transaction.atomic() if apply else nullcontext():
            with schema_context("public"):
                if apply:
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '5s'")
                        cursor.execute("SET LOCAL statement_timeout = '60s'")
                        cursor.execute("LOCK TABLE core_tenant IN SHARE MODE")
                tenants = list(Tenant.objects.exclude(schema_name="public").order_by("id").values("id", "public_id", "slug", "schema_name"))
            groups = defaultdict(list)
            for tenant in tenants:
                groups[tenant["schema_name"]].append(tenant)

            existing = []
            for schema in sorted(groups):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname=%s", [schema])
                    tables = {row[0] for row in cursor.fetchall()}
                    required = {model._meta.db_table for model in MODELS.values()}
                    if not required.issubset(tables):
                        raise CommandError(f"Incomplete CMS tables in schema {schema}: {sorted(required - tables)}")
                    if apply:
                        quoted = ", ".join(f"{connection.ops.quote_name(schema)}.{connection.ops.quote_name(table)}" for table in sorted(required))
                        cursor.execute(f"LOCK TABLE {quoted} IN SHARE ROW EXCLUSIVE MODE")
                existing.append(schema)

            backups, plans = {}, {}
            for schema in existing:
                with schema_context(schema):
                    backups[schema] = snapshot()
                plans[schema] = plan_schema_repair(groups[schema], backups[schema]["pages"], backups[schema]["sections"])

            summary = {
                "tenant_count": len(tenants),
                "schema_count": len(existing),
                "page_changes": sum(len(plan["pages"]) for plan in plans.values()),
                "section_changes": sum(len(plan["sections"]) for plan in plans.values()),
                "unscoped_pages_preserved": sum(row["tenant_id"] is None for data in backups.values() for row in data["pages"]),
            }
            self.stdout.write(json.dumps({"mode": "apply" if apply else "dry-run", "summary": summary, "plans": plans}, cls=DjangoJSONEncoder))
            if options["backup_path"]:
                payload = json.dumps({"created_at": datetime.now(timezone.utc), "tenants": tenants, "schemas": backups, "plans": plans}, cls=DjangoJSONEncoder, sort_keys=True).encode()
                fd = os.open(options["backup_path"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as backup:
                    backup.write(payload)
                    backup.flush()
                    os.fsync(backup.fileno())
                self.stdout.write(f"Backup: {options['backup_path']} sha256={hashlib.sha256(payload).hexdigest()}")
            if not apply:
                return

            for schema, plan in plans.items():
                with schema_context(schema):
                    for name in ("pages", "sections"):
                        for change in plan[name]:
                            updated = MODELS[name].objects.filter(id=change["id"], tenant_id=change["old"]).update(tenant_id=change["new"])
                            if updated != 1:
                                raise CommandError(f"Concurrent ownership change: {schema}/{name}/{change['id']}")
                    after = snapshot()
                    expected = json.loads(json.dumps(backups[schema], cls=DjangoJSONEncoder))
                    for name in ("pages", "sections"):
                        targets = {change["id"]: change["new"] for change in plan[name]}
                        for row in expected[name]:
                            if row["id"] in targets:
                                row["tenant_id"] = targets[row["id"]]
                    if expected != json.loads(json.dumps(after, cls=DjangoJSONEncoder)):
                        raise CommandError(f"Content verification failed in schema {schema}; rolling back.")
                    remaining = plan_schema_repair(groups[schema], after["pages"], after["sections"])
                    if any(remaining.values()):
                        raise CommandError(f"Ownership repair incomplete in schema {schema}; rolling back.")
        self.stdout.write(self.style.SUCCESS("Committed ownership backfill; all CMS contents verified unchanged."))
