# ArnaSite — QA Walkthrough

Dokumen ini adalah panduan QA step-by-step untuk memvalidasi ArnaSite di staging maupun production.

**Prinsip QA:**
- Gunakan **dedicated QA tenant** saja — tidak ada akses ke tenant customer
- **Read-only terlebih dahulu**, write hanya saat diperlukan dan reversible
- Tidak ada destructive operation tanpa approval eksplisit

---

## 1. Perubahan Arsitektur dari Versi Sebelumnya

| Hal | Sebelumnya | Sekarang |
|-----|-----------|---------|
| Autentikasi | Dual: SSO round-trip + JWT lokal | **JWT lokal saja** (RS256, offline) |
| API surface | Tenant API + Admin API (`/site-admin/api/`) | **Satu API terpadu** — RBAC dari JWT claims |
| Struktur konten | Sections → Blocks → Items | **Pages → Sections → Blocks → Items** |
| URL prefix | `/api/sites/sections/`, `/api/tenants/current/` | `/api/pages/`, `/api/tenant/` |
| Port | `8002` | **`8001`** |
| Register tenant | Manual via shell | `POST /tenants/register/` (public API) |
| Template | Hanya sistem | Sistem + **tenant bisa buat template sendiri** |

---

## 2. Safety Rules

Sebelum mulai, konfirmasi:

- [ ] Menggunakan tenant QA yang didedikasikan (bukan tenant customer)
- [ ] Ada approval untuk window QA ini
- [ ] Token yang disiapkan adalah token JWT dari Arna SSO yang valid
- [ ] Tidak akan menjalankan operasi destruktif tanpa written approval

**Operasi yang DILARANG tanpa explicit approval:**

- `overwrite=true` pada apply-template
- `DELETE` pages, sections, blocks, items, files
- Publish/unpublish template di lingkungan production customer
- Upload/abort berulang pada file produksi nyata

---

## 3. URL Structure Referensi

### Public API (`root-domain`)

```
GET  /templates/                Katalog template (no auth)
GET  /templates/{id}/           Detail template (no auth)
POST /tenants/register/         Daftarkan tenant baru (JWT is_owner required)
GET  /swagger/                  Swagger UI
```

### Tenant API (`tenant-domain`)

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

# Files
GET                /api/files/
POST               /api/files/init-upload/
GET  PATCH  DELETE /api/files/{id}/
POST               /api/files/{id}/presign/
POST               /api/files/{id}/complete/
POST               /api/files/{id}/abort/

# Pages (nested recursive)
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
GET  /api/public/site/          Daftar halaman aktif
GET  /api/public/site/{slug}/   Konten lengkap satu halaman
```

---

## 4. Postman Setup

### Environment Variables

Buat dua Postman environment: **ArnaSite Public QA** dan **ArnaSite Tenant QA**.

| Variable | Contoh | Keterangan |
|----------|--------|-----------|
| `root_url` | `https://app.arnasite.id` | Root domain (public schema) |
| `tenant_url` | `https://qa.arnasite.id` | Domain tenant QA |
| `token` | `eyJhbGci...` | JWT dari Arna SSO |
| `template_id` | `uuid` | ID template untuk apply/test |
| `page_id` | `uuid` | ID page QA |
| `section_id` | `uuid` | ID section QA |
| `block_id` | `uuid` | ID block QA |
| `item_id` | `uuid` | ID item QA |
| `file_id` | `uuid` | ID file QA |

### Header untuk semua request berautentikasi

```
Authorization: Bearer {{token}}
Content-Type: application/json
```

### Token claims yang diperlukan

Sebelum mulai, decode token dan pastikan:
- `org_id` terisi (bukan null) — harus terdaftar sebagai tenant
- `is_owner: true` **atau** `roles: ["site_admin"]` — untuk write operations
- `exp` belum lewat

```js
// Decode di browser console
JSON.parse(atob('{{token}}'.split('.')[1]))
```

---

## 5. QA Checklist — Public API

Base URL: `{{root_url}}`

### 5.1 Swagger UI

| # | Request | Expected |
|---|---------|---------|
| 1 | `GET {{root_url}}/swagger/` | 200, Swagger UI terbuka |
| 2 | Cek endpoint list | Hanya tampil: `/templates/`, `/tenants/register/` |
| 3 | Cek tombol Authorize | Hanya ada form **Bearer** (tidak ada Basic Auth) |
| 4 | Cek security definition | `Bearer: apiKey in header` |

### 5.2 Template Catalog

| # | Request | Expected |
|---|---------|---------|
| 5 | `GET {{root_url}}/templates/` | 200, array of templates |
| 6 | Verifikasi struktur | Setiap item punya `pages[].sections[].blocks[]` |
| 7 | `GET {{root_url}}/templates/{{template_id}}/` | 200, detail template lengkap |
| 8 | `GET {{root_url}}/templates/invalid-uuid/` | 404 |
| 9 | Pastikan hanya `is_published=true` muncul | Tidak ada template private di daftar |

### 5.3 Tenant Register (no auth test)

| # | Request | Expected |
|---|---------|---------|
| 10 | `POST {{root_url}}/tenants/register/` tanpa token | 401 `Bearer token required` |
| 11 | `POST {{root_url}}/tenants/register/` dengan token yang `org_id=null` | 403 `Token tidak menyertakan org_id...` |
| 12 | `POST {{root_url}}/tenants/register/` dengan `is_owner=false` | 403 `Hanya owner organisasi...` |

---

## 6. QA Checklist — Tenant API

Base URL: `{{tenant_url}}`

### 6.1 Swagger UI

| # | Request | Expected |
|---|---------|---------|
| 13 | `GET {{tenant_url}}/swagger/` | 200, Swagger UI terbuka |
| 14 | Cek endpoint list | Tampil: `/api/pages/`, `/api/tenant/`, `/api/templates/`, `/api/files/`, `/api/public/` |
| 15 | Tidak ada endpoint `/site-admin/` | ✅ harus tidak ada |

### 6.2 Autentikasi — Negative Tests

| # | Request | Expected |
|---|---------|---------|
| 16 | `GET {{tenant_url}}/api/pages/` tanpa header | 401 |
| 17 | `GET {{tenant_url}}/api/pages/` dengan token `Bearer invalid` | 401 `Invalid or expired JWT token` |
| 18 | `GET {{tenant_url}}/api/pages/` dengan token org lain | 403 (IsTenantMember gagal) |

### 6.3 Tenant Info (Read)

| # | Request | Expected |
|---|---------|---------|
| 19 | `GET {{tenant_url}}/api/tenant/` | 200, `name`, `slug`, `schema_name`, `domains[]` |
| 20 | `GET {{tenant_url}}/api/domains/` | 200, list domain tenant |

### 6.4 Pages (Read)

| # | Request | Expected |
|---|---------|---------|
| 21 | `GET {{tenant_url}}/api/pages/` | 200, list pages |
| 22 | `GET {{tenant_url}}/api/pages/{{page_id}}/` | 200, detail page dengan `sections[]` embed |
| 23 | Verifikasi scoping | Data hanya milik tenant QA, tidak ada data tenant lain |

### 6.5 Sections (Read Nested)

| # | Request | Expected |
|---|---------|---------|
| 24 | `GET {{tenant_url}}/api/pages/{{page_id}}/sections/` | 200, list sections |
| 25 | `GET {{tenant_url}}/api/pages/{{page_id}}/sections/{{section_id}}/` | 200, detail section |
| 26 | `GET {{tenant_url}}/api/pages/invalid-uuid/sections/` | 404 |

### 6.6 Blocks & Items (Read Nested)

| # | Request | Expected |
|---|---------|---------|
| 27 | `GET {{tenant_url}}/api/pages/{{page_id}}/sections/{{section_id}}/blocks/` | 200 |
| 28 | `GET {{tenant_url}}/api/pages/{{page_id}}/sections/{{section_id}}/blocks/{{block_id}}/` | 200 |
| 29 | `GET {{tenant_url}}/api/pages/{{page_id}}/sections/{{section_id}}/blocks/{{block_id}}/items/` | 200 |

### 6.7 Templates (Browse)

| # | Request | Expected |
|---|---------|---------|
| 30 | `GET {{tenant_url}}/api/templates/` | 200, semua template (public + milik tenant) |
| 31 | `GET {{tenant_url}}/api/templates/?visibility=public` | 200, hanya `is_published=true` |
| 32 | `GET {{tenant_url}}/api/templates/?visibility=private` | 200, hanya milik tenant ini |

### 6.8 Files (Read)

| # | Request | Expected |
|---|---------|---------|
| 33 | `GET {{tenant_url}}/api/files/` | 200, list media references |
| 34 | `GET {{tenant_url}}/api/files/{{file_id}}/` | 200, detail file |

### 6.9 Public Site (No Auth)

| # | Request | Expected |
|---|---------|---------|
| 35 | `GET {{tenant_url}}/api/public/site/` | 200 tanpa Authorization header |
| 36 | Verifikasi struktur | `{ tenant: {...}, pages: [...] }` |
| 37 | `GET {{tenant_url}}/api/public/site/home/` | 200, konten lengkap halaman home |
| 38 | Verifikasi struktur page | `sections[].blocks[].items[]` |
| 39 | `GET {{tenant_url}}/api/public/site/tidak-ada/` | 404 |
| 40 | Verifikasi `is_active=false` section tidak muncul | ✅ hanya section aktif |

---

## 7. QA Checklist — Write Operations (Minimal, Reversible)

Lakukan hanya pada dedicated QA tenant. Catat semua ID yang dibuat untuk cleanup.

### 7.1 Create Page

```json
POST {{tenant_url}}/api/pages/
{
  "title": "QA Test Page",
  "is_active": true,
  "order": 99
}
```

| Expected | |
|----------|--|
| Status | 201 |
| Response | `{ id, title, slug: "qa-test-page", ... }` |
| Verifikasi | Muncul di `GET /api/pages/` |

Simpan `page_id` dari response.

### 7.2 Create Section di Page

```json
POST {{tenant_url}}/api/pages/{{new_page_id}}/sections/
{
  "type": "hero",
  "order": 1,
  "is_active": true
}
```

| Expected | |
|----------|--|
| Status | 201 |
| Verifikasi | `section.page == new_page_id` |

### 7.3 Create Block di Section

```json
POST {{tenant_url}}/api/pages/{{new_page_id}}/sections/{{new_section_id}}/blocks/
{
  "title": "QA Hero Title",
  "subtitle": "QA subtitle",
  "order": 1
}
```

| Expected | |
|----------|--|
| Status | 201 |

### 7.4 Create Item di Block

```json
POST {{tenant_url}}/api/pages/{{new_page_id}}/sections/{{new_section_id}}/blocks/{{new_block_id}}/items/
{
  "title": "QA Feature",
  "icon": "check",
  "order": 1
}
```

| Expected | |
|----------|--|
| Status | 201 |
| Verifikasi | Item muncul di `GET .../blocks/{{id}}/items/` |

### 7.5 Reorder Pages

```json
PATCH {{tenant_url}}/api/pages/reorder/
[
  {"id": "{{new_page_id}}", "order": 98}
]
```

| Expected | |
|----------|--|
| Status | 200, `{ "status": "reordered" }` |
| Verifikasi | Order berubah di GET list |

### 7.6 Reorder Sections

```json
PATCH {{tenant_url}}/api/pages/{{new_page_id}}/sections/reorder/
[
  {"id": "{{new_section_id}}", "order": 2}
]
```

| Expected | |
|----------|--|
| Status | 200 |

### 7.7 Unauthorized Write Test

```json
POST {{tenant_url}}/api/pages/
Authorization: Bearer <token_dengan_role_kosong_tapi_valid>
```

| Expected | |
|----------|--|
| Status | 403 (IsTenantAdmin / IsTenantOwner gagal) |

### 7.8 Apply Template (hanya jika QA tenant kosong)

```json
POST {{tenant_url}}/api/tenant/apply-template/
{
  "template_id": "{{template_id}}",
  "overwrite": false
}
```

| Expected | |
|----------|--|
| Status | 200, `{ "status": "template applied successfully" }` |
| Verifikasi | `GET /api/pages/` mengembalikan pages dari template |
| Catatan | Jika tenant sudah punya konten: 409 Conflict → jangan gunakan `overwrite: true` di production |

### 7.9 Storage — Init Upload

```json
POST {{tenant_url}}/api/files/init-upload/
{
  "filename": "qa-test.png",
  "mime_type": "image/png",
  "size_bytes": 1024,
  "owner_scope": "org",
  "visibility": "private"
}
```

| Expected | |
|----------|--|
| Status | 201 |
| Response | `{ reference_id, multipart: { upload_id, parts: [{part_number, presign_url}] }, url }` |

### 7.10 Storage — Abort (cleanup test artifact)

```json
POST {{tenant_url}}/api/files/{{reference_id}}/abort/
```

| Expected | |
|----------|--|
| Status | 200, `{ "status": "aborted" }` |

---

## 8. QA Checklist — Template Management

### 8.1 Buat Template Private

```json
POST {{tenant_url}}/api/templates/
{
  "name": "QA Test Template",
  "slug": "qa-test-template",
  "description": "Template untuk QA",
  "category": "test"
}
```

| Expected | |
|----------|--|
| Status | 201 |
| `is_published` | `false` |
| `source_tenant_schema` | schema tenant QA |

### 8.2 Verifikasi Tidak Muncul di Katalog Public

| # | Request | Expected |
|---|---------|---------|
| | `GET {{root_url}}/templates/` | Template QA tidak muncul |
| | `GET {{tenant_url}}/api/templates/?visibility=private` | Template QA muncul |

### 8.3 Publish Template

```json
POST {{tenant_url}}/api/templates/{{qa_template_id}}/publish/
```

| Expected | |
|----------|--|
| Status | 200, `{ "status": "published", "is_published": true }` |
| Verifikasi | Muncul di `GET {{root_url}}/templates/` |

### 8.4 Unpublish Template (cleanup)

```json
DELETE {{tenant_url}}/api/templates/{{qa_template_id}}/publish/
```

| Expected | |
|----------|--|
| Status | 200, `{ "status": "unpublished", "is_published": false }` |
| Verifikasi | Tidak muncul lagi di `GET {{root_url}}/templates/` |

---

## 9. Cleanup

Setelah QA selesai, hapus semua artefak QA:

```
DELETE {{tenant_url}}/api/pages/{{new_page_id}}/
  → CASCADE menghapus sections, blocks, items

DELETE {{tenant_url}}/api/templates/{{qa_template_id}}/

# File yang di-abort sudah bersih di S3, tidak perlu delete record
```

Catat:
- ID semua objek yang dibuat
- Apakah semua berhasil dihapus
- Jika ada yang tidak bisa dihapus, escalate

---

## 10. Response Validation Checklist

Untuk setiap response, verifikasi:

- [ ] HTTP status sesuai ekspektasi
- [ ] Data hanya milik tenant QA (tidak ada data tenant lain)
- [ ] Tidak ada endpoint `/site-admin/api/` yang muncul di Swagger manapun
- [ ] Swagger Authorize hanya menampilkan form **Bearer** (tidak ada Basic Auth)
- [ ] Error response format: `{ "error": "..." }` atau `{ "detail": "..." }`
- [ ] Nested URL constraint bekerja (section di page lain → 404)

---

## 11. Evidence yang Harus Dikumpulkan

Untuk sign-off, kumpulkan:

- [ ] Screenshot Swagger public (`/swagger/`) — hanya tampil public endpoints
- [ ] Screenshot Swagger tenant (`/swagger/`) — hanya tampil tenant endpoints
- [ ] Request/response dari minimal write test (create page + section + block + item)
- [ ] Request/response dari negative auth tests (401, 403)
- [ ] Request/response dari public site read (`/api/public/site/{slug}/`)
- [ ] Log cleanup (ID yang dibuat dan dikonfirmasi terhapus)
- [ ] Timestamp tiap step
- [ ] Domain tenant yang digunakan
- [ ] Claims JWT yang digunakan (cukup `org_id`, `is_owner`, `roles` — jangan expose full token)

---

## 12. Sign-Off Checklist

QA dinyatakan selesai hanya jika semua item berikut terpenuhi:

| Item | Status |
|------|--------|
| Public Swagger terbuka dan hanya tampil endpoint publik | |
| Tenant Swagger terbuka dan hanya tampil endpoint tenant | |
| Tidak ada endpoint `/site-admin/api/` di manapun | |
| Authorize Swagger hanya menampilkan Bearer (tidak Basic Auth) | |
| JWT valid → akses berhasil | |
| JWT tanpa `org_id` → 403 dengan pesan jelas | |
| JWT tanpa auth header → 401 | |
| Token org lain → 403 (IsTenantMember) | |
| Member tanpa role → GET berhasil, POST/PATCH/DELETE → 403 | |
| Owner/admin → semua write berhasil | |
| `GET /api/public/site/{slug}/` berhasil tanpa auth | |
| `GET /api/public/site/tidak-ada/` → 404 | |
| Create page → 201, muncul di list | |
| Nested section/block/item → 201, data terisolasi per page | |
| Reorder → 200, urutan berubah | |
| Storage init-upload → 201 dengan presign URL | |
| Storage abort → 200 | |
| Template private tidak muncul di katalog root | |
| Template publish/unpublish bekerja | |
| Cleanup semua artefak QA selesai | |
| Evidence tersimpan | |

---

## 13. Catatan untuk Operator

- **Jangan pernah** gunakan tenant customer untuk QA.
- Selalu gunakan token dengan `org_id` yang sesuai dengan tenant QA.
- Jika ada 500 error → cek server log sebelum melanjutkan.
- Jika Redis tidak tersedia → JWT tetap berfungsi (fallback tanpa cache), catat sebagai warning.
- `overwrite=true` pada apply-template adalah **operasi destruktif** — butuh explicit approval.
- Jika ada behavior yang tidak terduga, **stop dan escalate** sebelum melanjutkan.
