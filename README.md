# ArnaSite

A **multi-tenant website CMS backend** built with Django and django-tenants. Each organization gets an isolated PostgreSQL schema. Content managers interact via a standard tenant API (SSO token → /auth/me validation), while tenant administrators get a dedicated Admin API secured by **local RS256 JWT verification** — no SSO round-trip per request.

## Table of Contents

- [Features](#features)
- [Technology Stack](#technology-stack)
- [Architecture Overview](#architecture-overview)
- [Quick Start (Docker)](#quick-start-docker)
- [Environment Variables](#environment-variables)
- [Authentication](#authentication)
- [API Reference](#api-reference)
  - [Public Schema](#public-schema-root-domain)
  - [Tenant Schema — Tenant API (SSO Auth)](#tenant-schema-tenant-api-sso-auth)
  - [Tenant Schema — Admin API (JWT Auth)](#tenant-schema-admin-api-jwt-auth)
- [Swagger / API Docs](#swagger--api-docs)
- [Running Tests](#running-tests)
- [Tenant Onboarding](#tenant-onboarding)
- [Docker Compose Services](#docker-compose-services)
- [Related Services](#related-services)

---

## Features

- **Multi-Tenancy** — Each organization gets a fully isolated PostgreSQL schema via django-tenants
- **Dual Authentication** — SSO proxy auth (for general users) and local JWT verification (for admin endpoints)
- **Role-Based Admin Access** — `site_admin` role or org owner (`is_owner`) grants admin API access, decoded from JWT claims
- **CMS Content Management** — Hierarchical Sections → ContentBlocks → ListItems, fully CRUD
- **Section Reordering** — Bulk atomic reorder endpoint with UUID validation
- **Template System** — Master templates cloned into tenant schemas on demand, with overwrite protection
- **File Storage** — S3-backed upload proxy via Arna File Manager (presigned URL flow)
- **Redis Caching** — SSO user sessions and JWT token resolutions cached to minimize external calls
- **Auto-Seeding** — Public tenant and default template created automatically on first migration

---

## Technology Stack

| Library | Purpose |
|---------|---------|
| Django 5 | Web framework |
| Django REST Framework | API layer |
| django-tenants | PostgreSQL schema-based multi-tenancy |
| PyJWT (RS256) | Local JWT verification for Admin API |
| cryptography | RSA key operations |
| Redis | Caching (SSO sessions + JWT token cache) |
| uWSGI + Supervisor | Production app server |
| drf-yasg | Swagger / OpenAPI documentation |
| whitenoise | Static file serving |

---

## Architecture Overview

```
                         ┌──────────────────────────────────────┐
  Browser / Frontend     │            ArnaSite (8002)           │
  ─────────────────────► │                                      │
                         │  ┌─────────────┐  ┌──────────────┐  │
  JWT (from Arna SSO)    │  │  Admin API  │  │  Tenant API  │  │
  ─────────────────────► │  │  /admin/api │  │  /api/sites  │  │
                         │  │             │  │              │  │
                         │  │ JWT decoded │  │ token → SSO  │  │
                         │  │  locally    │  │  /auth/me    │  │
                         │  │  (RS256)    │  │              │  │
                         │  └─────────────┘  └──────────────┘  │
                         │        ↓                  ↓          │
                         │  ┌────────────────────────────────┐  │
                         │  │  Per-tenant PostgreSQL Schema  │  │
                         │  │  Sections → Blocks → Items     │  │
                         │  └────────────────────────────────┘  │
                         └──────────────────────────────────────┘
                                           ↑
                              Arna SSO (JWT issuance + /auth/me)
```

---

## Quick Start (Docker)

```bash
# 1. Clone the repo
git clone https://github.com/ardzix/arna_site.git && cd arna_site

# 2. Copy and configure environment
cp .env.example .env
# Edit .env to match your setup (see Environment Variables below)

# 3. Place the Arna SSO public key (needed for Admin API JWT verification)
mkdir -p ssl
cp /path/to/arna_sso/public.pem ssl/public.pem

# 4. Start all services
docker-compose up -d --build

# 5. Run database migrations (creates all schemas)
docker exec arna_site_web python manage.py migrate_schemas

# 6. Confirm it's running
curl http://localhost:8002/templates/
```

The API is now available at **http://localhost:8002**.
Swagger UI (tenant API): **http://localhost:8002/swagger/**
Swagger UI (admin API): **http://localhost:8002/site-admin/api/swagger/**

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(required)* | Django secret key |
| `DEBUG` | `False` | Enable debug mode |
| `DB_NAME` | `arna_site` | PostgreSQL database name |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | `postgres` | PostgreSQL password |
| `DB_HOST` | `localhost` | DB host (`postgres` inside Docker) |
| `DB_PORT` | `5432` | DB port |
| `REDIS_URL` | `redis://localhost:6379/1` | Redis connection URL |
| `ARNA_SSO_BASE_URL` | `https://sso.arnatech.id/api` | Arna SSO base URL |
| `ARNA_STORAGE_BASE_URL` | `https://storage.arnatech.id` | Arna File Manager base URL |
| `SSO_USER_CACHE_TTL` | `300` | SSO token→user cache TTL (seconds) |
| `SSO_JWT_PUBLIC_KEY_PATH` | `/app/ssl/public.pem` | Path to Arna SSO RSA public key (Admin API) |
| `SSO_JWT_AUDIENCE` | `arnasite` | Expected JWT audience claim |
| `PUBLIC_DOMAIN_NAME` | `localhost` | Root domain for the public tenant (auto-seeded) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins |

---

## Authentication

ArnaSite uses **two authentication backends**, one per API surface:

### 1. `ArnaSSOAuthentication` — Tenant API

Used by `/api/sites/`, `/api/storage/`, `/api/tenants/`.

Flow per request:
1. Extracts `Authorization: Bearer <token>` from the request.
2. Calls Arna SSO `/auth/me/` to validate the token and get user info.
3. Calls `/organizations/current/` to identify the active organization + roles.
4. Looks up the matching `Tenant` by `sso_organization_id`.
5. Caches the resolved user object in Redis for `SSO_USER_CACHE_TTL` seconds.

### 2. `ArnaJWTAuthentication` — Admin API

Used exclusively by `/site-admin/api/`.

Flow per request:
1. Extracts `Authorization: Bearer <token>` from the request.
2. **Decodes the JWT locally** using the Arna SSO RSA public key (RS256, no network call).
3. Validates required claims: `exp`, `user_id`, `org_id`, and `aud: arnasite`.
4. Looks up the matching `Tenant` by `org_id`.
5. Caches the resolved user in Redis for **60 seconds** (keyed by SHA-256 of the token).

> **Why two backends?** The Admin API is optimized for performance — local JWT decode avoids an SSO round-trip on every request. Trade-off: roles/permissions reflect what was in the token at issuance; stale data is bounded by JWT lifetime.

### Permission Layers (Admin API)

```
IsAuthenticated         — valid user object present
  + IsTenantMember      — user's org_id matches current tenant's schema
  + (IsTenantAdmin      — user has 'site_admin' in JWT roles
  |  IsTenantOwner)     — OR user.is_owner == True
```

---

## API Reference

### Project Structure

```
config/
├── urls.py              # Root URL dispatcher
├── admin_urls.py        # Admin API routes (/site-admin/api/)
└── public_urls.py       # Public schema routes (/templates/)

core/                    # Public schema — tenant & template management
sites/                   # Tenant schema — CMS content (sections, blocks, items)
storage/                 # Tenant schema — file upload proxy
authentication/          # Shared — authentication backends + permissions
```

---

### Public Schema (root domain)

Base URL: `http://localhost:8002` (or your root domain)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/templates/` | No | List all master templates |
| `GET` | `/templates/<id>/` | No | Template detail with full section/block structure |
| `GET` | `/swagger/` | No | Swagger UI (public API) |

---

### Tenant Schema — Tenant API (SSO Auth)

Base URL: `http://<tenant-domain>:8002`
Auth: `Authorization: Bearer <arna-sso-access-token>`

#### Site Rendering (Public — no auth required)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/site/` | No | Full page structure for public-facing rendering |

#### CMS — Sections

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/sites/sections/` | SSO | List all sections |
| `POST` | `/api/sites/sections/` | SSO | Create a section |
| `GET` | `/api/sites/sections/<id>/` | SSO | Section detail |
| `PATCH` | `/api/sites/sections/<id>/` | SSO | Update a section |
| `DELETE` | `/api/sites/sections/<id>/` | SSO | Delete a section |

#### CMS — Blocks

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/sites/blocks/` | SSO | List blocks (filter: `?section=<id>`) |
| `POST` | `/api/sites/blocks/` | SSO | Create a block |
| `GET/PATCH/DELETE` | `/api/sites/blocks/<id>/` | SSO | Block detail / update / delete |
| `GET` | `/api/sites/sections/<id>/blocks/` | SSO | Blocks nested under a section |
| `POST` | `/api/sites/sections/<id>/blocks/` | SSO | Create block under section |

#### CMS — List Items

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/sites/items/` | SSO | List items (filter: `?block=<id>`) |
| `POST` | `/api/sites/items/` | SSO | Create a list item |
| `GET/PATCH/DELETE` | `/api/sites/items/<id>/` | SSO | Item detail / update / delete |
| `GET` | `/api/sites/blocks/<id>/items/` | SSO | Items nested under a block |

#### Templates

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/tenants/current/apply-template/` | SSO | Clone a master template into this tenant's schema |

Request body:
```json
{
  "template_id": "<uuid>",
  "overwrite": false
}
```

Responses: `200 OK` on success, `409 Conflict` if content already exists (use `"overwrite": true` to force).

#### Storage

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/storage/files/init-upload/` | SSO | Initialize S3 presigned upload |
| `POST` | `/api/storage/files/<id>/confirm-upload/` | SSO | Mark upload as complete |
| `GET` | `/api/storage/files/` | SSO | List all media references |
| `GET` | `/api/storage/files/<id>/` | SSO | Media reference detail |

Init upload request body:
```json
{
  "display_name": "company-logo.png",
  "mime_type": "image/png",
  "size_bytes": 204800
}
```

---

### Tenant Schema — Admin API (JWT Auth)

Base URL: `http://<tenant-domain>:8002/site-admin/api/`
Auth: `Authorization: Bearer <arna-sso-jwt-token>`
Required role: **`site_admin`** in JWT `roles` claim, or **`is_owner: true`**

> **Swagger UI:** [`/site-admin/api/swagger/`](http://localhost:8002/site-admin/api/swagger/)

This API surface is identical in capability to the Tenant API but uses **local JWT decode** — no SSO round-trip per request. Intended for use by admin dashboards and content management tools.

#### Admin — Sections

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/site-admin/api/sections/` | JWT Admin | List all sections |
| `POST` | `/site-admin/api/sections/` | JWT Admin | Create a section |
| `GET` | `/site-admin/api/sections/<id>/` | JWT Admin | Section detail |
| `PATCH` | `/site-admin/api/sections/<id>/` | JWT Admin | Update a section |
| `DELETE` | `/site-admin/api/sections/<id>/` | JWT Admin | Delete a section |
| `PATCH` | `/site-admin/api/sections/reorder/` | JWT Admin | Bulk reorder sections |

Reorder request body:
```json
[
  { "id": "<section-uuid>", "order": 1 },
  { "id": "<section-uuid>", "order": 2 }
]
```

#### Admin — Content Blocks

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/site-admin/api/blocks/` | JWT Admin | List blocks (filter: `?section=<id>`) |
| `POST` | `/site-admin/api/blocks/` | JWT Admin | Create a block |
| `GET/PATCH/DELETE` | `/site-admin/api/blocks/<id>/` | JWT Admin | Block detail / update / delete |

#### Admin — List Items

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/site-admin/api/items/` | JWT Admin | List items (filter: `?block=<id>`) |
| `POST` | `/site-admin/api/items/` | JWT Admin | Create a list item |
| `GET/PATCH/DELETE` | `/site-admin/api/items/<id>/` | JWT Admin | Item detail / update / delete |

#### Admin — Storage

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/site-admin/api/storage/init-upload/` | JWT Admin | Initialize S3 presigned upload |
| `POST` | `/site-admin/api/storage/<id>/confirm-upload/` | JWT Admin | Confirm upload |
| `GET` | `/site-admin/api/storage/` | JWT Admin | List all media references |

#### Admin — Template Application

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/site-admin/api/tenants/current/apply-template/` | JWT Admin | Apply master template to tenant |

Request body:
```json
{
  "template_id": "<uuid>",
  "overwrite": false
}
```

#### Admin API — Error Reference

| HTTP | Scenario |
|------|----------|
| `401` | Missing or invalid JWT token |
| `401` | Expired token |
| `401` | Wrong audience (`aud` claim ≠ `arnasite`) |
| `401` | RS256 signature mismatch (wrong key) |
| `401` | Missing required claims (`user_id`, `org_id`, `exp`) |
| `403` | Valid token but `org_id` doesn't match current tenant |
| `403` | Valid token but no `site_admin` role and not `is_owner` |
| `404` | Template ID not found |
| `409` | Template already applied (use `overwrite: true`) |

---

## Swagger / API Docs

Two separate Swagger UIs are available:

| UI | URL | Covers |
|----|-----|--------|
| **Public + Tenant API** | `http://<host>:8002/swagger/` | `/templates/`, `/api/sites/`, `/api/storage/`, `/api/tenants/` |
| **Admin API** | `http://<host>:8002/site-admin/api/swagger/` | All `/site-admin/api/` endpoints (sections, blocks, items, storage, apply-template, reorder) |

The Admin API Swagger documents all endpoints with their required JWT bearer authentication. Use the **Authorize** button and enter:
```
Bearer <your-arna-sso-jwt-token>
```

---

## Running Tests

Tests require Docker services to be running (PostgreSQL + Redis).

```bash
# Start services if not already running
docker-compose up -d

# Run all tests
docker exec arna_site_web python manage.py test --verbosity=2

# Run a specific test module
docker exec arna_site_web python manage.py test sites.tests_admin --verbosity=2
docker exec arna_site_web python manage.py test authentication.tests --verbosity=2
```

**Test coverage:**

| Module | Test Class | What's Covered |
|--------|------------|----------------|
| `authentication` | `ArnaJWTAuthenticationTest` | No header, malformed bearer, wrong signature, expired token, missing claims, wrong audience, no matching tenant, valid token → SSOUser, cache hit, missing/invalid public key file |
| `authentication` | `ArnaSSOAuthenticationTest` | Roles/permissions populated, `/auth/me` failure, org API failure, tenant not found |
| `authentication` | `PermissionTest` | IsTenantAdmin pass/fail, IsTenantOwner pass/fail/missing attr, IsTenantMember null connection guard, regression: SSO user without site_admin role |
| `sites` | `AdminAPITest` | No token → 401, wrong signature → 401, authenticated but not admin → 403, wrong tenant → 403, full CRUD lifecycle, bulk reorder, invalid reorder payloads, reorder cross-tenant isolation, owner access, site_admin access, apply template, overwrite flow, nonexistent template, filter by block, cache hit |
| `core` | `CoreTests` | Template apply, missing/invalid template ID, unauthenticated access, idempotency |
| `sites` | `SiteTests` | Full CRUD lifecycle, block filtering, public site view, schema isolation |
| `storage` | `StorageTests` | Init upload, confirm upload, File Manager 502 handling |

---

## Tenant Onboarding

When a new organization registers via Arna SSO, onboard them with:

```bash
docker exec -it arna_site_web python manage.py shell
```

```python
from core.models import Tenant, Domain

tenant = Tenant.objects.create(
    schema_name='toko_budi',       # lowercase, underscores only
    name='Toko Budi',
    slug='toko-budi',
    sso_organization_id='<uuid-from-arna-sso>'
)
Domain.objects.create(
    domain='toko-budi.arna.com',
    tenant=tenant,
    is_primary=True
)
```

The PostgreSQL schema is created automatically on save. Run migrations for the new schema:

```bash
docker exec arna_site_web python manage.py migrate_schemas --schema=toko_budi
```

---

## Docker Compose Services

| Service | Container | Internal Port | Host Port |
|---------|-----------|---------------|-----------|
| Django app (uWSGI) | `arna_site_web` | `8002` | `8002` |
| PostgreSQL 15 | `arna_site_postgres` | `5432` | `5433` |
| Redis 7 | `arna_site_redis` | `6379` | `6380` |

---

## Related Services

| Service | Repo | Role |
|---------|------|------|
| **Arna SSO** | [`arna_sso`](https://github.com/ardzix/arna_sso) | Identity & access management, RS256 JWT issuance, RBAC |
| **Arna File Manager** | *(external)* | S3-backed file storage, presigned URL generation |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
