# ArnaSite Production QA Walkthrough

This document describes a safe, step-by-step QA process for ArnaSite in production.
It is written for a **Postman-oriented** workflow and is designed to minimize risk:
- use a **dedicated QA tenant** only
- perform **read-only checks first**
- allow only a **minimal reversible write** during QA
- avoid destructive operations unless there is explicit approval

## 1. Purpose

Validate that production ArnaSite is healthy across the three exposed API surfaces:

1. **Public Schema** — root domain
2. **Tenant API** — tenant domain with SSO access token
3. **Admin API** — tenant domain under `site-admin/api/` with local JWT verification

This walkthrough focuses on:
- reachability
- authentication and authorization
- read-only response correctness
- one minimal reversible write on the dedicated QA tenant
- storage integration sanity checks

## 2. Safety Rules for Production QA

Before starting, confirm the following:

- You are using a **dedicated QA tenant**.
- You are **not** testing on a customer tenant.
- You have approval for the specific QA window.
- You have the correct token type for each API surface.
- You will not run destructive actions unless explicitly approved.

### Do not run by default

Avoid these actions in production unless there is a written approval and rollback plan:

- `overwrite=true` on template apply
- `DELETE` on sections, blocks, items, profiles, or templates
- remote storage deletion tests beyond a controlled cleanup
- bulk CRUD or load tests
- repeated upload/abort cycles on real production files

## 3. API Surfaces and Base URLs

### Public Schema

- Base URL: `https://<root-domain>`
- Swagger: `https://<root-domain>/swagger/`
- Public template endpoints:
  - `GET /templates/`
  - `GET /templates/<id>/`
- Public site rendering endpoint:
  - `GET /public/site/`

### Tenant API

- Base URL: `https://<tenant-domain>`
- Swagger: `https://<tenant-domain>/swagger/`
- Uses SSO access token:
  - `Authorization: Bearer <arna-sso-access-token>`

Main endpoints:
- `GET /api/sites/sections/`
- `POST /api/sites/sections/`
- `GET /api/sites/sections/<id>/`
- `PATCH /api/sites/sections/<id>/`
- `GET /api/sites/blocks/`
- `POST /api/sites/blocks/`
- `GET /api/sites/items/`
- `POST /api/sites/items/`
- `PATCH /api/sites/sections/reorder/`
- `POST /api/tenants/current/apply-template/`
- `GET /api/storage/files/`
- `POST /api/storage/files/init-upload/`
- `POST /api/storage/files/<id>/presign/`
- `POST /api/storage/files/<id>/complete/`
- `POST /api/storage/files/<id>/abort/`

### Admin API

- Base URL: `https://<tenant-domain>/site-admin/api/`
- Swagger: `https://<tenant-domain>/site-admin/api/swagger/`
- Uses local RS256 JWT:
  - `Authorization: Bearer <arna-sso-jwt-token>`

Main endpoints:
- `GET /site-admin/api/sections/`
- `POST /site-admin/api/sections/`
- `GET /site-admin/api/sections/<id>/`
- `PATCH /site-admin/api/sections/<id>/`
- `PATCH /site-admin/api/sections/reorder/`
- `GET /site-admin/api/blocks/`
- `POST /site-admin/api/blocks/`
- `GET /site-admin/api/items/`
- `POST /site-admin/api/items/`
- `GET /site-admin/api/storage/`
- `POST /site-admin/api/storage/init-upload/`
- `POST /site-admin/api/storage/<id>/presign/`
- `POST /site-admin/api/storage/<id>/complete/`
- `POST /site-admin/api/storage/<id>/abort/`
- `POST /site-admin/api/tenants/current/apply-template/`

## 4. Postman Setup

Create or import a Postman collection with three request folders:

1. **Public Schema QA**
2. **Tenant API QA**
3. **Admin API QA**

Recommended environments:
- `ArnaSite Public QA`
- `ArnaSite Tenant QA`
- `ArnaSite Admin QA`

### Suggested environment variables

| Variable | Example |
|---|---|
| `root_base_url` | `https://example.com` |
| `tenant_base_url` | `https://qa-tenant.example.com` |
| `admin_base_url` | `https://qa-tenant.example.com/site-admin/api` |
| `sso_access_token` | `<SSO access token>` |
| `admin_jwt_token` | `<RS256 JWT token>` |
| `template_id` | `<uuid>` |
| `section_id` | `<uuid>` |
| `block_id` | `<uuid>` |
| `item_id` | `<uuid>` |
| `storage_id` | `<uuid>` |

### Common headers

For SSO-based requests:
- `Authorization: Bearer {{sso_access_token}}`
- `Content-Type: application/json`

For admin JWT requests:
- `Authorization: Bearer {{admin_jwt_token}}`
- `Content-Type: application/json`

### Postman request organization

Put requests in this order:
1. health and reachability checks
2. read-only GET checks
3. auth failure checks
4. controlled create/update checks
5. controlled cleanup checks

## 4.1 Local Automated Smoke Test (localhost)

For fast local verification on development machine:

- ArnaSite: `http://localhost:8002`
- SSO: `http://localhost:8001`

Run the script:

```bash
cd /Users/aqilamuzafa/Documents/GitHub/arnasite
bash scripts/qa_local_smoke.sh
```

Optional env vars:

```bash
SSO_BASE_URL=http://localhost:8001 \
ARNASITE_BASE_URL=http://localhost:8002 \
RUN_TENANT_ADMIN_CHECKS=1 \
AUTO_SSO_AUTH=1 \
AUTO_ADMIN_JWT_FROM_SSO=1 \
SSO_ORG_ID='<organization-uuid-optional>' \
TENANT_HOST='qa.localhost' \
SSO_TEST_EMAIL='qa_smoke_user@example.com' \
SSO_TEST_PASSWORD='SmokeTest123!' \
SSO_ACCESS_TOKEN='<sso-access-token>' \
ADMIN_JWT_TOKEN='<admin-jwt-token>' \
bash scripts/qa_local_smoke.sh
```

Notes:
- The script is API-only: it does not call `python manage.py shell` or touch the DB directly.
- Without token env vars, script can still run public read-only checks and SSO login/register.
- Tenant/Admin API checks are opt-in: set `RUN_TENANT_ADMIN_CHECKS=1`.
- Tenant/Admin checks require a preconfigured routable tenant host in `TENANT_HOST`.
- `AUTO_ADMIN_JWT_FROM_SSO=1` derives `ADMIN_JWT_TOKEN` from SSO token automatically.
- If `SSO_ORG_ID` is set, script calls `POST /api/organizations/current/` to mint org-context token.
- Do not pass placeholder values like `<your-org-uuid>`; use a real UUID.
- If org switch fails, script falls back to current SSO access token for admin checks.
- With tokens provided, script validates authenticated tenant/admin endpoints.
- Script exits non-zero when any check fails.
- If tenant routes are not mounted for `TENANT_HOST`, tenant/admin checks are skipped (not failed).

## 4.2 Negative Testing & Edge Cases

The local QA script also includes a negative test mode to validate that invalid input and unauthorized access are rejected correctly.

Representative negative cases:

- `POST /api/auth/register/` with missing email → `400`
- `POST /api/auth/register/` with invalid email → `400`
- `POST /api/auth/login/` with wrong password → `400`
- `GET /api/auth/me/` with invalid token → `401`
- `GET /templates/not-a-uuid/` → `404`
- `POST /api/tenants/current/apply-template/` with empty body → `400`
- `PATCH /api/sites/sections/reorder/` with invalid body → `400`
- `GET /site-admin/api/sections/` without JWT → `401`
- Admin JWT with wrong audience → `401`
- Admin JWT missing `org_id` → `401`
- Admin JWT with tampered signature → `401`

Run negative mode together with smoke mode by leaving `RUN_NEGATIVE_CHECKS=1`.

## 5. Step-by-Step QA Checklist

## 5.1 Public Schema QA

### Step 1 — Open Swagger

Request:
- `GET {{root_base_url}}/swagger/`

Expected:
- Swagger UI loads successfully
- only public schema endpoints are visible
- no `site-admin/api` endpoints appear

### Step 2 — List templates

Request:
- `GET {{root_base_url}}/templates/`

Expected:
- status `200`
- returns list of active templates
- response contains no tenant-private data

### Step 3 — View template detail

Request:
- `GET {{root_base_url}}/templates/{{template_id}}/`

Expected:
- status `200`
- returns nested template structure
- includes sections, blocks, and list items

### Step 4 — Public site render endpoint

Request:
- `GET {{tenant_base_url}}/public/site/`

Expected:
- status `200`
- returns tenant name/slug plus active sections
- no authentication required

## 5.2 Tenant API QA

### Step 1 — Open tenant Swagger

Request:
- `GET {{tenant_base_url}}/swagger/`

Expected:
- Swagger UI loads successfully
- only tenant-facing API endpoints are visible
- no admin routes are shown

### Step 2 — Read-only section list

Request:
- `GET {{tenant_base_url}}/api/sites/sections/`

Expected:
- status `200`
- returns only tenant data for the dedicated QA tenant

### Step 3 — Read-only block list with filter

Request:
- `GET {{tenant_base_url}}/api/sites/blocks/?section={{section_id}}`

Expected:
- status `200`
- returns blocks for the selected section only

### Step 4 — Read-only item list with filter

Request:
- `GET {{tenant_base_url}}/api/sites/items/?block={{block_id}}`

Expected:
- status `200`
- returns items for the selected block only

### Step 5 — Validate authorization failures

Run the same request without token.

Expected:
- status `401`

Run the same request with a token from the wrong tenant or invalid token.

Expected:
- status `403` or `401` depending on failure mode

### Step 6 — Minimal reversible write

Use only the dedicated QA tenant.

Recommended action:
- create one section or one block
- update its title/order once
- verify it appears in GET responses
- revert or delete only if the team has approval for cleanup

Example request:
- `POST {{tenant_base_url}}/api/sites/sections/`

Expected:
- status `201`
- object belongs to the QA tenant only

### Step 7 — Reorder sanity check

Request:
- `PATCH {{tenant_base_url}}/api/sites/sections/reorder/`

Example body:
```json
[
  {"id": "<section-uuid>", "order": 1},
  {"id": "<section-uuid>", "order": 2}
]
```

Expected:
- status `200`
- order changes are reflected in subsequent GET requests

### Step 8 — Template apply check

Only do this if the QA tenant is empty or designed for template QA.

Request:
- `POST {{tenant_base_url}}/api/tenants/current/apply-template/`

Body:
```json
{
  "template_id": "{{template_id}}",
  "overwrite": false
}
```

Expected:
- status `200`
- template is applied successfully
- no existing QA data is lost

Do not use `overwrite: true` unless explicitly approved.

## 5.3 Admin API QA

### Step 1 — Open admin Swagger

Request:
- `GET {{admin_base_url}}/swagger/`

Expected:
- Swagger UI loads successfully
- only admin API routes are shown

### Step 2 — Validate admin authorization

Use a valid admin JWT token.

Request:
- `GET {{admin_base_url}}/sections/`

Expected:
- status `200`
- response scoped to the current tenant

Use a non-admin token.

Expected:
- status `403`

Use no token.

Expected:
- status `401`

### Step 3 — List blocks and items

Requests:
- `GET {{admin_base_url}}/blocks/`
- `GET {{admin_base_url}}/items/`

Expected:
- status `200`
- only QA tenant data is visible

### Step 4 — Minimal admin write

Recommended reversible action:
- create one section
- update its title or order
- verify the result in GET responses

Example request:
- `POST {{admin_base_url}}/sections/`

Expected:
- status `201`
- object belongs to the QA tenant only

### Step 5 — Reorder check

Request:
- `PATCH {{admin_base_url}}/sections/reorder/`

Expected:
- status `200`
- order is updated atomically

### Step 6 — Storage sanity check

Request:
- `GET {{admin_base_url}}/storage/`

Expected:
- status `200`
- returns media references for the QA tenant only

### Step 7 — Storage upload flow, only if required

Use only if QA needs to validate file upload integration.

Flow:
1. `POST {{admin_base_url}}/storage/init-upload/`
2. `POST {{admin_base_url}}/storage/<id>/presign/`
3. `POST {{admin_base_url}}/storage/<id>/complete/`
4. `POST {{admin_base_url}}/storage/<id>/abort/` only for cleanup of a failed test

Expected:
- init upload returns `201`
- presign returns `200`
- complete returns updated media reference
- abort returns `200`

Avoid testing remote deletion in production unless explicitly approved.

## 6. Response Validation Checklist

For every request, confirm:

- HTTP status is expected
- response is scoped to the correct tenant
- no cross-tenant data appears
- no admin route appears in public Swagger
- no public route appears in admin Swagger
- IDs returned by create calls belong to the QA tenant only

## 7. Cleanup and Rollback

After the QA session:

- revert any temporary section/block/item created for QA
- confirm ordering is restored if it was changed
- abort unfinished uploads only for test artifacts
- record which objects were created and removed
- note any failed requests and the response body

If a destructive action was performed accidentally:
1. stop further changes
2. capture the exact request and response
3. escalate immediately
4. verify whether data restoration is required

## 8. Evidence to Capture

Capture the following evidence for sign-off:

- screenshots of both Swagger UIs
- request/response examples from Postman
- timestamps for each step
- tenant domain used
- token type used
- any error responses from auth checks
- before/after counts for created objects

## 9. QA Sign-off Checklist

Mark the QA as complete only if all of the following are true:

- public Swagger opens and shows only public endpoints
- tenant Swagger opens and shows only tenant API endpoints
- admin Swagger opens and shows only admin API endpoints
- SSO access token works for tenant API requests
- admin JWT works for admin API requests
- unauthenticated requests fail as expected
- unauthorized requests fail as expected
- minimal write test succeeds on the dedicated QA tenant
- cleanup is completed
- evidence is saved

## 10. Notes for Operators

- Use the dedicated QA tenant only.
- Keep the test surface small.
- Prefer read-only validation over write validation.
- Treat template overwrite and deletes as production-risk operations.
- If anything unexpected happens, stop and escalate.
