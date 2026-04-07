# arna-site

A **multi-tenant SaaS CMS backend** built with Django and `django-tenants`. Each business (UMKM) gets a fully isolated PostgreSQL schema. Authentication is handled externally by [Arna SSO](https://github.com/ardzix/arna_sso) — no local user table required.

---

## Architecture Overview

```
                   ┌─────────────────────────────┐
                   │         Arna SSO             │
                   │  /auth/me/  /organizations/  │
                   └────────────┬────────────────-┘
                                │ JWT validation
                   ┌────────────▼────────────────-┐
                   │        ArnaSite API           │
                   │  ┌──────────┐ ┌────────────┐ │
                   │  │ public   │ │  tenant    │ │
                   │  │ schema   │ │  schema    │ │
                   │  │Templates │ │ Sections   │ │
                   │  │Tenants   │ │ Blocks     │ │
                   │  └──────────┘ │ Storage    │ │
                   │               └────────────┘ │
                   └─────────────────────────────-┘
                                │
                   ┌────────────▼────────────────-┐
                   │      Arna File Manager        │
                   │  S3 presigned URL callbacks   │
                   └─────────────────────────────-┘
```

| Layer | Technology |
|-------|-----------|
| Framework | Django 5.0 + Django REST Framework |
| Multi-tenancy | `django-tenants` (PostgreSQL schema isolation) |
| Authentication | Arna SSO (JWT via `ArnaSSOAuthentication`) |
| Cache | Redis (SSO token caching, 5-min TTL) |
| Storage | Arna File Manager (S3 presigned URL proxy) |
| API Docs | drf-yasg (Swagger UI) |
| Database | PostgreSQL 15 |

---

## How Multi-Tenancy Works

- Every request hits `TenantMainMiddleware`, which resolves the **domain → tenant schema**.
- **Public schema** (`localhost`) — stores `Tenant`, `Domain`, and master `Template` blueprints. Served via `config/public_urls.py`.
- **Tenant schema** (e.g. `toko-budi.arna.com`) — stores `Section`, `ContentBlock`, `ListItem`, `MediaReference`. Served via `config/urls.py`.
- The `TenantSyncRouter` automatically routes ORM queries to the right schema.

---

## Project Structure

```
arnasite/
├── config/
│   ├── settings.py          # Django settings, SHARED_APPS / TENANT_APPS split
│   ├── urls.py              # Tenant URLconf (auth-required CMS + storage APIs)
│   └── public_urls.py       # Public URLconf (template catalog + public site render)
│
├── core/                    # Shared (public schema) — Tenant, Domain, Templates
│   ├── models.py            # Tenant, Domain, Template, TemplateSection, TemplateBlock
│   ├── serializers.py       # Nested template serializer
│   ├── services.py          # apply_template() — clones blueprint into tenant schema
│   ├── views.py             # TemplateListView, TemplateDetailView, ApplyTemplateView
│   └── tests.py
│
├── authentication/          # Shared — SSO token validation + permission class
│   ├── backends.py          # ArnaSSOAuthentication (validates via /auth/me/)
│   ├── permissions.py       # IsTenantMember (schema-match guard)
│   └── tests.py
│
├── sites/                   # Tenant — CMS content models
│   ├── models.py            # Section, ContentBlock, ListItem
│   ├── serializers.py       # Nested content serializers
│   ├── views.py             # ViewSets + PublicSiteView + nested block/item views
│   └── tests.py
│
├── storage/                 # Tenant — file upload proxy
│   ├── models.py            # MediaReference
│   ├── serializers.py
│   ├── views.py             # init-upload + confirm-upload proxy actions
│   └── tests.py
│
├── .env.example             # Environment variable reference
├── docker-compose.yml       # Local dev stack (web + postgres + redis)
└── requirements.txt
```

---

## Quick Start (Docker)

```bash
# 1. Clone the repo
git clone https://github.com/ardzix/arna_site.git
cd arna_site

# 2. Copy and configure environment
cp .env.example .env
# Edit .env if needed (defaults work for docker-compose)

# 3. Start all services
docker-compose up -d --build

# 4. Run database migrations
docker exec arna_site_web python manage.py migrate_schemas

# 5. Seed initial public tenant + test template
docker exec arna_site_web python manage.py seed_tenant

# 6. Confirm it's running
curl http://localhost:8002/templates/
```

The API is now available at **http://localhost:8002**.

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
| `SSO_USER_CACHE_TTL` | `300` | SSO token cache duration (seconds) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins |

---

## API Reference

### Public Schema (`localhost` / your root domain)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/templates/` | ❌ | List all active master templates |
| `GET` | `/templates/<id>/` | ❌ | Get a single template with full structure |
| `GET` | `/swagger/` | ❌ | Swagger UI (public API) |

### Tenant Schema (`<tenant>.arna.com`)

#### Site Rendering (Public)
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/site/` | ❌ | Get all active sections + blocks for public rendering |

#### CMS — Sections
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/sites/sections/` | ✅ | List all sections |
| `POST` | `/api/sites/sections/` | ✅ | Create a section |
| `GET` | `/api/sites/sections/<id>/` | ✅ | Get section detail |
| `PATCH` | `/api/sites/sections/<id>/` | ✅ | Update a section |
| `DELETE` | `/api/sites/sections/<id>/` | ✅ | Delete a section |

#### CMS — Blocks
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/sites/blocks/` | ✅ | List blocks (filter: `?section=<id>`) |
| `POST` | `/api/sites/blocks/` | ✅ | Create a block |
| `GET/PATCH/DELETE` | `/api/sites/blocks/<id>/` | ✅ | Block detail |

#### CMS — List Items
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/sites/items/` | ✅ | List items (filter: `?block=<id>`) |
| `POST` | `/api/sites/items/` | ✅ | Create a list item |
| `GET/PATCH/DELETE` | `/api/sites/items/<id>/` | ✅ | Item detail |

#### Templates
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/tenants/current/apply-template/` | ✅ | Clone a master blueprint into this tenant's schema |

**Request body:**
```json
{ "template_id": "<uuid>" }
```

#### Storage
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/storage/files/init-upload/` | ✅ | Initialize S3 presigned upload via File Manager |
| `POST` | `/api/storage/files/<id>/confirm-upload/` | ✅ | Confirm upload completed, mark reference as active |
| `GET` | `/api/storage/files/` | ✅ | List all media references |
| `GET` | `/api/storage/files/<id>/` | ✅ | Get media reference detail |

**Init upload request body:**
```json
{
  "display_name": "company-logo.png",
  "mime_type": "image/png",
  "size_bytes": 204800
}
```

#### API Docs
| Endpoint | Description |
|----------|-------------|
| `GET /swagger/` | Swagger UI (tenant APIs) |

---

## Authentication

All protected endpoints require a JWT bearer token issued by Arna SSO:

```
Authorization: Bearer <jwt_token>
```

The `ArnaSSOAuthentication` backend:
1. Calls `/auth/me/` to validate the token and get user info.
2. Calls `/organizations/current/` to identify the active organization.
3. Looks up the matching `Tenant` by `sso_organization_id`.
4. Caches the result in Redis for `SSO_USER_CACHE_TTL` seconds.

The `IsTenantMember` permission then verifies that the authenticated user's organization matches the **currently active tenant schema**, preventing cross-tenant data access.

---

## Running Tests

Tests require the Docker stack to be running (PostgreSQL + Redis).

```bash
# Start services if not already running
docker-compose up -d

# Run all tests
docker exec arna_site_web python manage.py test --verbosity=2
```

**Test coverage:**

| Module | Tests |
|--------|-------|
| `core` | E2E template clone, missing/invalid template ID, unauthenticated access, idempotency |
| `authentication` | Invalid token rejection, cross-tenant access prevention, no-auth header, valid token |
| `sites` | Full CRUD lifecycle, block filtering, public site view, schema isolation |
| `storage` | Init upload, confirm upload, File Manager 502 handling |

---

## Tenant Onboarding

When a new organization signs up via Arna SSO, onboard them with:

```bash
# Creates a new tenant row + PostgreSQL schema + domain mapping
python manage.py shell
```

```python
from core.models import Tenant, Domain
import uuid

tenant = Tenant.objects.create(
    schema_name='toko_budi',
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

The PostgreSQL schema `toko_budi` is created automatically on save (`auto_create_schema = True`). Run `migrate_schemas` afterward to provision all tenant tables:

```bash
python manage.py migrate_schemas --schema=toko_budi
```

---

## Docker Compose Services

| Service | Container | Port |
|---------|-----------|------|
| Django app | `arna_site_web` | `8002` |
| PostgreSQL 15 | `arna_site_postgres` | `5433` (host) |
| Redis 7 | `arna_site_redis` | `6380` (host) |

---

## Related Services

| Service | Repo | Role |
|---------|------|------|
| **Arna SSO** | [`arna_sso`](https://github.com/ardzix/arna_sso) | Identity & access management, JWT issuance |
| **Arna File Manager** | *(external)* | S3-backed file storage, presigned URL generation |
