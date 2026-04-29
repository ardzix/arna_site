# ArnaSite

Multi-tenant website CMS backend built with Django and django-tenants. Each organization (tenant) gets an **isolated PostgreSQL schema**, a dedicated subdomain, and a full CMS API to manage their website content.

Authentication is handled entirely offline via **RS256 JWT tokens** issued by Arna SSO — no SSO round-trip on every request.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Technology Stack](#technology-stack)
- [Architecture Overview](#architecture-overview)
- [Quick Start (Local)](#quick-start-local)
- [Quick Start (Docker)](#quick-start-docker)
- [Environment Variables](#environment-variables)
- [Authentication & RBAC](#authentication--rbac)
- [URL Structure](#url-structure)
- [Tenant Onboarding](#tenant-onboarding)
- [Template System](#template-system)
- [Running Tests](#running-tests)
- [AI Copilot](#ai-copilot)
- [Related Services](#related-services)

---

## How It Works

```
1. User logs in to Arna SSO → receives JWT token
   (token contains: user_id, org_id, roles, is_owner)

2. User sends request to ArnaSite with Bearer token
   → Middleware routes request to correct PostgreSQL schema based on domain
   → JWT verified locally using public.pem (RS256, no network call)
   → RBAC applied from JWT claims

3. Frontend reads /api/public/site/{slug} to render the website
   → No auth required for public endpoints
```

**Tenant isolation:** Every tenant (`yapu.arnasite.id`, `tokobudi.arnasite.id`) lives in its own PostgreSQL schema. There is zero data leakage between tenants — even at the DB query level.

---

## Technology Stack

| Library | Purpose |
|---------|---------|
| Django 5 | Web framework |
| Django REST Framework | API layer |
| django-tenants | PostgreSQL schema-based multi-tenancy |
| PyJWT (RS256) | Local JWT verification (no SSO round-trip) |
| psycopg2 | PostgreSQL adapter |
| Redis | JWT decode result caching |
| drf-yasg | Swagger / OpenAPI docs |
| django-cors-headers | CORS handling |

---

## Architecture Overview

```
                    ┌─────────────────────────────────────────────┐
  Browser /         │              ArnaSite                        │
  Frontend  ──────► │                                             │
                    │  Domain routing (TenantMainMiddleware)       │
  Bearer JWT        │  localhost        → public schema            │
  from Arna SSO     │  yapu.arnasite.id → yapu schema             │
                    │                                             │
                    │  ┌──────────────────────────────────────┐   │
                    │  │  ArnaJWTAuthentication               │   │
                    │  │  Decode JWT locally with public.pem  │   │
                    │  │  Extract: user_id, org_id, roles,    │   │
                    │  │          is_owner                    │   │
                    │  └──────────────────────────────────────┘   │
                    │              ↓                               │
                    │  ┌──────────────────────────────────────┐   │
                    │  │  RBAC Permission Classes             │   │
                    │  │  IsTenantMember  — org member        │   │
                    │  │  IsTenantAdmin   — has site_admin    │   │
                    │  │  IsTenantOwner   — is_owner=true     │   │
                    │  └──────────────────────────────────────┘   │
                    │              ↓                               │
                    │  ┌──────────────────────────────────────┐   │
                    │  │  Per-tenant PostgreSQL Schema        │   │
                    │  │  Pages → Sections → Blocks → Items  │   │
                    │  └──────────────────────────────────────┘   │
                    └─────────────────────────────────────────────┘
                                       ↑
                          Arna SSO (JWT issuance, RS256)
                          Arna File Manager (S3 storage)
```

**Data model hierarchy:**

```
[Public Schema]
Template
└── TemplatePage
    └── TemplateSection
        └── TemplateBlock
            └── TemplateListItem

[Tenant Schema]
Page  (slug: "home", "about", "pricing", ...)
└── Section  (type: "hero", "features", "team", ...)
    └── ContentBlock  (title, subtitle, description, image_url, extra:{})
        └── ListItem  (title, description, icon)
```

---

## Quick Start (Local)

### Prerequisites

- Python 3.12+
- PostgreSQL 15+
- Redis (optional — degrades gracefully if unavailable)

### Setup

```bash
# 1. Clone
git clone https://github.com/ardzix/arna_site.git && cd arna_site

# 2. Create virtualenv using official Python (not MinGW/MSYS2)
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 3. Install dependencies (skip uWSGI on Windows)
pip install -r requirements.txt

# 4. Copy and configure environment
cp .env.example .env
# Edit .env — minimum required: DB_*, SECRET_KEY, SSO_JWT_PUBLIC_KEY_PATH

# 5. Place the Arna SSO public key
cp /path/to/arna_sso/public.pem public.pem
# SSO_JWT_PUBLIC_KEY_PATH=public.pem  ← relative to project root (auto-resolved)

# 6. Run migrations
python manage.py migrate_schemas

# 7. Seed initial data (public tenant + test tenant + localhost domain)
python manage.py seed_tenant

# 8. Start the server
python manage.py runserver 8000
```

### Accessing Swagger

| URL | Schema | Covers |
|-----|--------|--------|
| `http://localhost:8000/swagger/` | Public | `/templates/`, `/tenants/register/` |
| `http://test.localhost:8000/swagger/` | Tenant | All CMS + storage + template endpoints |
| `http://yapu.localhost:8000/swagger/` | Tenant | (after registering yapu tenant) |

> **Windows hosts file** (`C:\Windows\System32\drivers\etc\hosts`):
> ```
> 127.0.0.1   test.localhost
> 127.0.0.1   yapu.localhost
> ```

---

## Quick Start (Docker)

```bash
# 1. Copy and configure environment
cp .env.example .env

# 2. Place the Arna SSO public key
cp /path/to/arna_sso/public.pem public.pem

# 3. Start all services
docker-compose up -d --build

# 4. Run migrations + seed
docker exec arna_site_web python manage.py migrate_schemas
docker exec arna_site_web python manage.py seed_tenant

# 5. Confirm
curl http://localhost:8000/templates/
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(required)* | Django secret key |
| `DEBUG` | `False` | Enable debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,.localhost` | Comma-separated |
| `DB_ENGINE` | `django.db.backends.postgresql` | DB engine |
| `DB_NAME` | `arna_site_db` | PostgreSQL database name |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | *(required)* | PostgreSQL password |
| `DB_HOST` | `localhost` | DB host |
| `DB_PORT` | `5432` | DB port |
| `REDIS_URL` | `redis://127.0.0.1:6379/1` | Redis connection URL |
| `ARNA_STORAGE_BASE_URL` | `https://storage.arnatech.id` | Arna File Manager base URL |
| `SSO_JWT_PUBLIC_KEY_PATH` | `public.pem` | Path to Arna SSO RSA public key |
| `SSO_JWT_AUDIENCE` | `arnasite` | Expected JWT audience (optional) |
| `CORS_ALLOWED_ORIGINS` | `https://app.arnasite.id` | Comma-separated CORS origins |

---

## Authentication & RBAC

### Token Flow

```
FE → Arna SSO login → JWT token
JWT token → ArnaSite API header: Authorization: Bearer <token>
ArnaSite → verifies with public.pem (RS256, offline)
ArnaSite → extracts claims → applies RBAC
```

### JWT Claims Used

| Claim | Type | Usage |
|-------|------|-------|
| `user_id` | UUID string | User identity |
| `org_id` | UUID string | Maps to tenant schema |
| `roles` | string[] | e.g. `["site_admin"]` |
| `is_owner` | bool | Full tenant ownership |
| `exp` | timestamp | Token expiry |

### Permission Matrix

| Action | IsTenantMember | IsTenantAdmin | IsTenantOwner |
|--------|:-:|:-:|:-:|
| Read content (GET) | ✅ | — | — |
| Create/edit content (POST/PATCH) | ✅ | ✅ | ✅ |
| Delete content (DELETE) | ✅ | ✅ | ✅ |
| Publish template | ✅ | ✅ | ✅ |
| Manage domains | ✅ | ✅ | ✅ |

---

## URL Structure

### Public API (`localhost:8000`)

```
GET  /templates/              List master templates (no auth)
GET  /templates/{id}/         Template detail (no auth)
POST /tenants/register/       Register new tenant (is_owner JWT required)
GET  /swagger/
```

### Tenant API (`{tenant-domain}:8000`)

```
# Tenant info
GET  PATCH  /api/tenant/
POST        /api/tenant/apply-template/

# Domains
GET  POST          /api/domains/
DELETE             /api/domains/{id}/

# Templates
GET  POST          /api/templates/          ?visibility=public|private
GET  PATCH  DELETE /api/templates/{id}/
POST  DELETE       /api/templates/{id}/publish/

# Files (S3 via Arna File Manager)
GET                /api/files/
POST               /api/files/init-upload/
GET  PATCH  DELETE /api/files/{id}/
POST               /api/files/{id}/presign/
POST               /api/files/{id}/complete/
POST               /api/files/{id}/abort/

# Pages (recursive)
GET  POST          /api/pages/
PATCH              /api/pages/reorder/
GET  PATCH  DELETE /api/pages/{page_id}/
GET  POST          /api/pages/{page_id}/sections/
PATCH              /api/pages/{page_id}/sections/reorder/
GET  PATCH  DELETE /api/pages/{page_id}/sections/{section_id}/
GET  POST          /api/pages/{page_id}/sections/{section_id}/blocks/
GET  PATCH  DELETE /api/pages/{page_id}/sections/{section_id}/blocks/{block_id}/
GET  POST          /api/pages/{page_id}/sections/{section_id}/blocks/{block_id}/items/
GET  PATCH  DELETE /api/pages/{page_id}/sections/{section_id}/blocks/{block_id}/items/{item_id}/

# Public (no auth)
GET  /api/public/site/          List active pages
GET  /api/public/site/{slug}/   Full page content (sections → blocks → items)
```

---

## Tenant Onboarding

**Via API (recommended):**

```bash
POST http://localhost:8000/tenants/register/
Authorization: Bearer <owner-jwt-token>

{
  "name": "Toko Budi",
  "slug": "toko-budi",
  "domain": "toko-budi.arnasite.id"
}
```

For local dev, add a `.localhost` domain after registering:

```python
# python manage.py shell
from core.models import Domain, Tenant
t = Tenant.objects.get(slug='toko-budi')
Domain.objects.create(domain='toko-budi.localhost', tenant=t, is_primary=False)
```

Then add to hosts file: `127.0.0.1   toko-budi.localhost`

---

## Template System

Templates are stored in the **public schema** and can be cloned to any tenant.

```
[Public Schema]
Template (is_published=True → visible in catalog)
└── TemplatePage ("Home", "About", ...)
    └── TemplateSection (type: "hero", "features", ...)
        └── TemplateBlock
            └── TemplateListItem
```

**Tenants can also create their own templates:**
1. `POST /api/templates/` → creates private template (`is_published=false`)
2. Add pages/sections/blocks/items to the template
3. `POST /api/templates/{id}/publish/` → visible in global catalog

**Applying a template:**

```bash
POST /api/tenant/apply-template/
{ "template_id": "<uuid>", "overwrite": false }
```

This clones the entire template structure into the tenant's schema (Pages → Sections → Blocks → Items).

---

## Running Tests

```bash
# Local
python manage.py test --verbosity=2

# Docker
docker exec arna_site_web python manage.py test --verbosity=2
```

---

## AI Copilot

ArnaSite now includes an `ai_helper` module for AI-assisted template and site generation.

Highlights:
- Tenant-scoped copilot sessions with chat history
- Multimodal brainstorming support (text + image URLs)
- Draft generation and schema validation before publish
- Publish flow into existing Template and Site models
- FE guide draft generation (`markdown`) for frontend implementation
- Async job execution for message/generate/publish with job status endpoint

Detailed implementation and API docs:
- `AI-COPILOT.md`
- `AI-IMPLEMENTATION-PLAN.md`
- `ai_schemas/README.md`

Runtime note:
- Start Django Q2 worker cluster in a separate process:
  - `python manage.py qcluster`

---

## Project Structure

```
arna_site/
├── config/
│   ├── settings.py         Django settings
│   ├── urls.py             Tenant schema URL router
│   └── public_urls.py      Public schema URL router
│
├── core/                   Public schema — tenant & template management
│   ├── models.py           Tenant, Domain, Template, TemplatePage, ...
│   ├── serializers.py
│   ├── views.py
│   ├── services.py         apply_template() logic
│   ├── tenant_urls.py      /api/tenant/
│   ├── domain_urls.py      /api/domains/
│   ├── template_urls.py    /api/templates/
│   └── register_urls.py    /tenants/register/ (public)
│
├── sites/                  Tenant schema — CMS content
│   ├── models.py           Page, Section, ContentBlock, ListItem
│   ├── serializers.py
│   ├── views.py
│   └── urls.py             /api/pages/ (nested)
│
├── storage/                Tenant schema — file management
│   ├── models.py           MediaReference
│   ├── serializers.py
│   ├── views.py            S3 upload proxy
│   └── urls.py             /api/files/
│
├── authentication/
│   ├── backends.py         SSOUser proxy
│   ├── jwt_backends.py     ArnaJWTAuthentication
│   └── permissions.py      IsTenantMember, IsTenantAdmin, IsTenantOwner
│
└── public.pem              Arna SSO RS256 public key (not committed)
```

---

## Related Services

| Service | Role |
|---------|------|
| **Arna SSO** | Identity, JWT issuance (RS256), org & role management |
| **Arna File Manager** | S3-backed file storage, presigned URL generation |
