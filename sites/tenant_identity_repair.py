"""Plan the legacy integer-as-UUID ownership backfill without guessing owners."""

import uuid


def plan_schema_repair(tenants, pages, sections):
    aliases = {}
    for tenant in tenants:
        current = str(tenant["public_id"])
        for alias in (current, str(uuid.UUID(int=tenant["id"]))):
            if alias in aliases and aliases[alias] != current:
                raise ValueError(f"Tenant identity collision: {alias}")
            aliases[alias] = current

    def owner(row):
        value = row["tenant_id"]
        if value is None:
            return None
        value = str(value)
        if value not in aliases:
            raise ValueError(f"Unknown owner {value} on record {row['id']}")
        return aliases[value]

    changes = {"pages": [], "sections": []}
    page_owners = {}
    active_slugs = set()
    for page in pages:
        target = owner(page)
        page_owners[str(page["id"])] = target
        if target and page["is_active"]:
            key = (target, page["slug"])
            if key in active_slugs:
                raise ValueError(f"Duplicate active slug after repair: {key}")
            active_slugs.add(key)
        if target and str(page["tenant_id"]) != target:
            changes["pages"].append({"id": str(page["id"]), "old": str(page["tenant_id"]), "new": target})

    for section in sections:
        target = owner(section)
        if section["page_id"] is not None:
            page_id = str(section["page_id"])
            if page_id not in page_owners:
                raise ValueError(f"Missing parent page for section {section['id']}")
            parent_owner = page_owners[page_id]
            if target and parent_owner and target != parent_owner:
                raise ValueError(f"Cross-tenant section {section['id']}")
            # A known parent is authoritative for an unscoped child. Never
            # assign an unscoped page or orphan to an arbitrary shared tenant.
            if target is None:
                target = parent_owner
        if target and str(section["tenant_id"]) != target:
            changes["sections"].append({"id": str(section["id"]), "old": str(section["tenant_id"]) if section["tenant_id"] else None, "new": target})

    return changes
