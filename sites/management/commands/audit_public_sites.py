"""Read-only inventory and public API/HTTP verification for every tenant."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from django.core.management.base import BaseCommand
from django.test import Client, override_settings
from django_tenants.utils import schema_context

from core.models import Domain, Tenant
from sites.models import Page


def check_http(task):
    tenant, domain, has_content = task
    url = f"https://{domain}/"
    result = {"tenant": tenant, "domain": domain, "has_content": has_content, "url": url}
    try:
        response = requests.get(url, timeout=(5, 20))
        result.update(status=response.status_code, final_url=response.url)
        title = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.S)
        result["title"] = title.group(1) if title else ""
        result["template_error"] = any(marker in response.text for marker in ("Template Not Found", "Template tidak ditemukan:", "The requested template component could not be loaded."))
        result["ok"] = response.ok and not result["template_error"]
    except requests.RequestException as exc:
        result.update(ok=False, error=str(exc))
    return result


class Command(BaseCommand):
    help = "Audit all tenant public API routing, page ownership and optional public website HTTP responses."

    def add_arguments(self, parser):
        parser.add_argument("--http", action="store_true")
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        with schema_context("public"):
            tenants = list(Tenant.objects.exclude(schema_name="public").order_by("id"))
            domains = list(Domain.objects.exclude(tenant__schema_name="public").order_by("domain").values("domain", "tenant_id", "role", "status"))
        report = {"checked_at": datetime.now(timezone.utc).isoformat(), "tenants": [], "http": []}
        tasks = []
        with override_settings(ALLOWED_HOSTS=["*"]):
            for tenant in tenants:
                tenant_domains = [domain for domain in domains if domain["tenant_id"] == tenant.id]
                backend = next((d["domain"] for d in tenant_domains if d["role"] == Domain.ROLE_BACKEND_PRIMARY), None)
                with schema_context(tenant.schema_name):
                    pages = list(Page.objects.filter(tenant_id=tenant.public_id, is_active=True).prefetch_related("sections").order_by("order", "title"))
                    expected_ids = {str(page.id) for page in pages}
                    row = {"slug": tenant.slug, "tenant_id": str(tenant.public_id), "schema": tenant.schema_name, "backend": backend, "active_pages": len(pages), "domains": tenant_domains, "pages": [], "errors": []}
                    for page in pages:
                        if any(section.tenant_id != tenant.public_id for section in page.sections.all()):
                            row["errors"].append(f"Section ownership differs on {page.slug}")
                        row["pages"].append({"id": str(page.id), "slug": page.slug, "template_id": str(page.source_template_id) if page.source_template_id else None, "sections": len(page.sections.all())})
                if backend:
                    client = Client(HTTP_HOST=backend)
                    response = client.get("/api/public/site/")
                    row["api_status"] = response.status_code
                    if response.status_code != 200:
                        row["errors"].append(f"Public list HTTP {response.status_code}")
                    else:
                        data = response.json()
                        if data.get("tenant", {}).get("slug") != tenant.slug:
                            row["errors"].append("Public list resolved another tenant")
                        if {page["id"] for page in data.get("pages", [])} != expected_ids:
                            row["errors"].append("Public list differs from owned active pages")
                    for page in row["pages"]:
                        detail = client.get(f"/api/public/site/{page['slug']}/")
                        if detail.status_code != 200 or detail.json().get("id") != page["id"]:
                            row["errors"].append(f"Public detail failed: {page['slug']}")
                        elif detail.json().get("template_id") != page["template_id"]:
                            row["errors"].append(f"Template mapping differs: {page['slug']}")
                    if not pages:
                        # A real slug in the shared pool must remain invisible
                        # to an empty neighboring tenant after the backfill.
                        probe = client.get("/api/public/site/home/")
                        if probe.status_code != 404:
                            row["errors"].append("Empty tenant can access a home page")
                else:
                    row["errors"].append("No registered backend primary domain")
                report["tenants"].append(row)
                for domain in tenant_domains:
                    name = domain["domain"]
                    if domain["role"] != Domain.ROLE_BACKEND_PRIMARY and not name.endswith(".localhost") and name != "localhost":
                        tasks.append((tenant.slug, name, bool(pages)))
            if options["http"]:
                with ThreadPoolExecutor(max_workers=6) as pool:
                    report["http"] = list(pool.map(check_http, tasks))
        report["summary"] = {
            "tenants": len(report["tenants"]),
            "tenants_with_content": sum(row["active_pages"] > 0 for row in report["tenants"]),
            "active_pages": sum(row["active_pages"] for row in report["tenants"]),
            "tenant_api_failures": sum(bool(row["errors"]) for row in report["tenants"]),
            "websites_checked": len(report["http"]),
            "content_website_failures": sum(row["has_content"] and not row["ok"] for row in report["http"]),
            "empty_tenant_websites": sum(not row["has_content"] for row in report["http"]),
        }
        with open(options["output"], "w", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
        self.stdout.write(json.dumps(report["summary"]))
        for row in report["tenants"]:
            if row["errors"]:
                self.stdout.write(json.dumps({"tenant": row["slug"], "errors": row["errors"]}))
        for row in report["http"]:
            if row["has_content"] and not row["ok"]:
                self.stdout.write(json.dumps(row))
