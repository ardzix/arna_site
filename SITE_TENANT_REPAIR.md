# Legacy public site ownership repair

After `core.0007_tenant_public_id`, public site queries use `Tenant.public_id`.
Legacy Page and Section rows can still contain `UUID(int=Tenant.id)`, making
existing sites appear empty even though their content and templates exist.

Run the audit and backfill explicitly against the deployed database:

```sh
python -m unittest sites.test_tenant_identity_repair
python manage.py repair_site_tenant_ids
python manage.py repair_site_tenant_ids --apply --backup-path /secure/new-site-ownership-backup.json
python manage.py repair_site_tenant_ids
python manage.py audit_public_sites --http --output /secure/site-audit.json
```

The repair only translates known tenant identities within each registered
schema. It rejects ambiguous owners, cross-tenant parent/child relationships,
and duplicate active slugs. Unscoped historical pages stay unscoped. No tenant
gets another tenant's content and no empty tenant gets invented pages.

Apply requires a new exclusive backup path. The transaction locks tenant and
CMS tables, persists a complete 0600 snapshot before writing, and verifies all
Page, Section, ContentBlock, and ListItem fields after writing. Only the planned
ownership fields may differ. The second dry run must report zero changes.
The commands do not run automatically on application startup or migration.

The audit checks each registered tenant's public list and detail APIs against
its owned active pages, checks section ownership, and verifies empty neighbors
cannot read another tenant's home page. Optional HTTP checks cover registered
non-backend domains and detect template fallback messages. A custom domain may
point to a separate application, so assess HTTP failures alongside domain
routing rather than automatically treating them as ArnaSite outages.

## Production recovery, 8 October 2026

- Audited 66 tenants in 10 schemas.
- Repaired 22 Pages and 174 Sections belonging to 18 legacy tenants.
- Verified all other CMS fields were unchanged and the repair was idempotent.
- Confirmed 19 tenants have 26 active pages; 47 have no active pages.
- Frontend PR https://github.com/ardzix/arna_site_fe/pull/64 restores three
  original missing template components: BBC Fitness, Kurnia Catering, and
  Catering Ibu Dewi. All 26 active page template IDs exist in that build.
- Replaced BBC's sole localhost image reference with the verified original
  File Manager asset, both in the site block and its source template block.

Production snapshots and logs are retained on the production server in
`/root/arna_site/repair-20261008/`:

- `site-identity-before.json`: initial dry-run snapshot.
- `site-identity-apply.json`: locked snapshot taken immediately before apply.
  SHA256 `ff80ad63ebeb42c6563f0c98084dbcf178b3a4e96a71d5eb2373526c93bcf02a`.
- `bbc-image-before.json`: exact old/new URL and block identifiers.
- `apply.log`: transaction verification result.

Rollback, if ever needed, must compare the current owner to each planned new
owner and revert only those ownership fields under the same table locks.
Do not overwrite whole rows from a historical snapshot: that would discard
subsequent tenant edits. Keep backups private; they contain tenant CMS content.
