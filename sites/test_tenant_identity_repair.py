"""Regression tests that need no production database or Django configuration."""

import unittest
import uuid

from sites.tenant_identity_repair import plan_schema_repair


class TenantIdentityRepairTest(unittest.TestCase):
    def setUp(self):
        self.a, self.b = str(uuid.uuid4()), str(uuid.uuid4())
        self.tenants = [{"id": 23, "public_id": self.a}, {"id": 25, "public_id": self.b}]
        self.old_a, self.old_b = str(uuid.UUID(int=23)), str(uuid.UUID(int=25))

    def page(self, pk, owner, slug="home"):
        return {"id": pk, "tenant_id": owner, "slug": slug, "is_active": True}

    def section(self, pk, owner, page=None):
        return {"id": pk, "tenant_id": owner, "page_id": page}

    def test_same_slug_in_shared_schema_stays_separate_and_is_idempotent(self):
        pages = [self.page("a", self.old_a), self.page("b", self.old_b)]
        sections = [self.section("sa", self.old_a, "a"), self.section("sb", self.old_b, "b")]
        plan = plan_schema_repair(self.tenants, pages, sections)
        self.assertEqual([row["new"] for row in plan["pages"]], [self.a, self.b])
        self.assertEqual([row["new"] for row in plan["sections"]], [self.a, self.b])
        for rows, changes in ((pages, plan["pages"]), (sections, plan["sections"])):
            for row, change in zip(rows, changes):
                row["tenant_id"] = change["new"]
        self.assertEqual(plan_schema_repair(self.tenants, pages, sections), {"pages": [], "sections": []})

    def test_unscoped_history_is_preserved_and_child_inherits_known_parent(self):
        pages = [self.page("old", None), self.page("a", self.a)]
        sections = [self.section("old-section", None, "old"), self.section("sa", None, "a")]
        plan = plan_schema_repair(self.tenants, pages, sections)
        self.assertEqual(plan["pages"], [])
        self.assertEqual(plan["sections"], [{"id": "sa", "old": None, "new": self.a}])

    def test_orphan_legacy_section_is_mapped_without_creating_pages(self):
        plan = plan_schema_repair(self.tenants, [], [self.section("s", self.old_a)])
        self.assertEqual(plan["sections"][0]["new"], self.a)

    def test_cross_tenant_child_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Cross-tenant"):
            plan_schema_repair(self.tenants, [self.page("a", self.old_a)], [self.section("s", self.old_b, "a")])

    def test_unknown_owner_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown owner"):
            plan_schema_repair(self.tenants, [self.page("a", str(uuid.uuid4()))], [])

    def test_duplicate_slug_during_partial_migration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate active slug"):
            plan_schema_repair(self.tenants, [self.page("a", self.old_a), self.page("b", self.a)], [])

    def test_identity_alias_collision_is_rejected(self):
        self.tenants[1]["public_id"] = self.old_a
        with self.assertRaisesRegex(ValueError, "identity collision"):
            plan_schema_repair(self.tenants, [], [])

    def test_foreign_schema_owner_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown owner"):
            plan_schema_repair(self.tenants[:1], [self.page("b", self.old_b)], [])
