# ArnaSite — Frontend Implementation Guide

Dokumen ini ditujukan untuk **Frontend Engineer** yang membangun:
1. **Tenant Dashboard** — antarmuka untuk content manager/owner mengelola website mereka
2. **Public Site** — website yang di-render dari konten tenant untuk pengunjung umum

---

## Table of Contents

- [Authentication Flow](#authentication-flow)
- [API Base URLs](#api-base-urls)
- [Dashboard — Recommended Architecture](#dashboard--recommended-architecture)
- [Dashboard — Layout & Navigation](#dashboard--layout--navigation)
- [Dashboard — Halaman per Fitur](#dashboard--halaman-per-fitur)
- [Public Site — Rendering Engine](#public-site--rendering-engine)
- [Section Type → Component Mapping](#section-type--component-mapping)
- [File Upload Flow](#file-upload-flow)
- [Error Handling](#error-handling)
- [Local Development Setup](#local-development-setup)

---

## Authentication Flow

```
1. User → Arna SSO login page
2. Arna SSO → redirect back dengan JWT token (access + refresh)
3. FE simpan token di memory / httpOnly cookie
4. Setiap request ke ArnaSite: header Authorization: Bearer <token>
5. Token expired → gunakan refresh token ke Arna SSO untuk token baru
```

**Informasi dari JWT (bisa di-decode di FE untuk UI purposes, bukan untuk keputusan keamanan):**

```js
// Decode payload (jangan jadikan sumber trust untuk auth!)
const payload = JSON.parse(atob(token.split('.')[1]));

payload.user_id    // UUID user
payload.org_id     // UUID organisasi → menentukan tenant mana yang diakses
payload.roles      // ["site_admin"] atau []
payload.is_owner   // true / false
payload.exp        // Unix timestamp expiry
```

**Navigasi awal berdasarkan token:**

```
org_id == null  → arahkan ke halaman "Buat Organisasi" atau error
is_owner == true → tampilkan menu owner (domains, publish template, dll)
roles.includes("site_admin") → tampilkan menu admin (edit konten)
selainnya → tampilkan mode read-only
```

---

## API Base URLs

```
Base URL dashboard : https://{tenant-slug}.arnasite.id
Base URL public    : https://{tenant-slug}.arnasite.id/api/public
Base URL register  : https://app.arnasite.id  (root domain)
```

Seluruh request CMS memerlukan header:
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

---

## Dashboard — Recommended Architecture

```
Tech stack yang direkomendasikan:
- Next.js 14+ (App Router)
- TanStack Query v5 (server state)
- Zustand (client state: sidebar collapse, drag state)
- shadcn/ui + Tailwind CSS
- dnd-kit (drag & drop reorder)
- react-hook-form + zod (form validation)
```

**Struktur folder:**

```
app/
├── (auth)/
│   └── login/               SSO redirect
│
├── (dashboard)/
│   ├── layout.tsx            Shell: Sidebar + Topbar
│   ├── page.tsx              Overview / Home
│   ├── pages/
│   │   ├── page.tsx          Daftar halaman
│   │   └── [pageId]/
│   │       ├── page.tsx      Page builder
│   │       └── sections/
│   │           └── [sectionId]/
│   │               └── page.tsx  Section editor
│   ├── templates/
│   │   ├── page.tsx          Browse & buat template
│   │   └── [templateId]/
│   │       └── page.tsx      Template editor
│   ├── files/
│   │   └── page.tsx          Media library
│   ├── domains/
│   │   └── page.tsx          Domain management
│   └── settings/
│       └── page.tsx          Tenant settings
│
└── [slug]/                   Public site renderer
    ├── page.tsx              Homepage (is_home=true)
    └── [pageSlug]/
        └── page.tsx          Page lainnya
```

---

## Dashboard — Layout & Navigation

```
┌────────────────────────────────────────────────────────────────┐
│  TOPBAR                                                        │
│  [Logo ArnaSite]          [Nama Tenant ▾]  [Avatar] [Notif]   │
├──────────────┬─────────────────────────────────────────────────┤
│              │  BREADCRUMB: Dashboard / Pages / Home           │
│  SIDEBAR     ├─────────────────────────────────────────────────┤
│              │                                                 │
│  Overview    │  MAIN CONTENT AREA                              │
│  ─────────── │                                                 │
│  📄 Pages    │                                                 │
│  🎨 Templates│                                                 │
│  🗂 Files    │                                                 │
│  ─────────── │                                                 │
│  ⚙ Settings │                                                 │
│  🌐 Domains  │                                                 │
│  ─────────── │                                                 │
│  👤 Profile  │                                                 │
│              │                                                 │
└──────────────┴─────────────────────────────────────────────────┘
```

**Sidebar item visibility berdasarkan role:**

| Menu Item | Member | Admin | Owner |
|-----------|:------:|:-----:|:-----:|
| Overview | ✅ | ✅ | ✅ |
| Pages (read) | ✅ | ✅ | ✅ |
| Pages (edit) | ✗ | ✅ | ✅ |
| Templates (browse) | ✅ | ✅ | ✅ |
| Templates (create/publish) | ✗ | ✅ | ✅ |
| Files (read) | ✅ | ✅ | ✅ |
| Files (upload) | ✗ | ✅ | ✅ |
| Domains | ✗ | ✅ | ✅ |
| Settings | ✗ | ✅ | ✅ |

---

## Dashboard — Halaman per Fitur

### 1. Overview

```
┌──────────────────────────────────────────────────────────────┐
│  Selamat datang, {user.name}                                 │
│  Tenant: {tenant.name}  ({tenant.slug}.arnasite.id)  [↗]    │
├────────────┬────────────┬──────────────┬─────────────────────┤
│ 3 Pages    │ 2 Templates│ 12 Files     │ 2 Domains           │
├────────────┴────────────┴──────────────┴─────────────────────┤
│  Quick Actions                                               │
│  [+ Buat Halaman]  [Pilih Template]  [Upload File]          │
├──────────────────────────────────────────────────────────────┤
│  Halaman Aktif                                               │
│  Home    /home    [Edit] [Lihat ↗]                          │
│  About   /about   [Edit] [Lihat ↗]                          │
└──────────────────────────────────────────────────────────────┘
```

**API calls:**
```
GET /api/tenant/          → nama tenant, slug
GET /api/pages/           → jumlah dan daftar halaman
GET /api/templates/       → jumlah template
GET /api/files/           → jumlah file
GET /api/domains/         → daftar domain
```

---

### 2. Pages — Daftar Halaman

```
┌──────────────────────────────────────────────────────────────┐
│  Pages                                    [+ Halaman Baru]   │
├──────────────────────────────────────────────────────────────┤
│  ≡  🏠 Home      /home     Aktif    [Edit] [Preview] [...]  │
│  ≡  📄 About     /about    Aktif    [Edit] [Preview] [...]  │
│  ≡  💰 Pricing   /pricing  Draft    [Edit] [Preview] [...]  │
│                                                              │
│  ≡ = drag handle untuk reorder                              │
└──────────────────────────────────────────────────────────────┘
```

**API calls:**
```
GET   /api/pages/            → list semua pages
POST  /api/pages/            → buat halaman baru
PATCH /api/pages/reorder/    → simpan urutan baru (dnd-kit)
DELETE /api/pages/{id}/      → hapus halaman
```

**Reorder payload:**
```js
// Saat user drop untuk reorder
await api.patch('/api/pages/reorder/', pages.map((p, i) => ({
  id: p.id,
  order: i + 1
})))
```

---

### 3. Page Builder

Ini adalah layar utama. Tampilkan sections sebagai blok yang bisa di-expand, edit, dan reorder.

```
┌──────────────────────────────────────────────────────────────┐
│  ← Back   Home (/home)   [is_home ✓]   [Aktif ✓]  [Save]  │
├────────────────────────────┬─────────────────────────────────┤
│  SECTIONS                  │  EDITOR                         │
│                            │                                 │
│  ≡  [hero]        [▾][⋮]  │  Section: hero                  │
│  ≡  [features]    [▾][⋮]  │  ─────────────────────────────  │
│  ≡  [team]        [▾][⋮]  │  Block #1                       │
│  ≡  [contact]     [▾][⋮]  │  Title: [__________________]    │
│                            │  Subtitle: [________________]   │
│  [+ Tambah Section]        │  Description: [______________]  │
│                            │                [______________]  │
│                            │  Image: [Upload / URL]          │
│                            │  Extra (JSON): [{              }]│
│                            │                                 │
│                            │  [+ Tambah Block]               │
│                            │                                 │
│                            │  ── List Items ──               │
│                            │  ≡ Cepat   bolt   [Edit][✕]    │
│                            │  ≡ Aman    shield [Edit][✕]    │
│                            │  [+ Tambah Item]                │
└────────────────────────────┴─────────────────────────────────┘
```

**API calls:**
```
GET  /api/pages/{id}/                         → page detail + sections embed
GET  /api/pages/{id}/sections/                → list sections per page
POST /api/pages/{id}/sections/                → tambah section baru
PATCH /api/pages/{id}/sections/reorder/       → reorder sections

GET  /api/pages/{id}/sections/{sid}/blocks/          → list blocks
POST /api/pages/{id}/sections/{sid}/blocks/          → tambah block
PATCH /api/pages/{id}/sections/{sid}/blocks/{bid}/   → edit block

GET  /api/pages/{id}/sections/{sid}/blocks/{bid}/items/         → list items
POST /api/pages/{id}/sections/{sid}/blocks/{bid}/items/         → tambah item
PATCH /api/pages/{id}/sections/{sid}/blocks/{bid}/items/{iid}/  → edit item
```

**Catatan UX:**
- Edit inline dengan auto-save (debounce 800ms) atau tombol Save eksplisit
- Upload gambar: gunakan flow `/api/files/init-upload/` → PUT ke presigned URL → `/api/files/{id}/complete/` → pakai URL yang dikembalikan
- `extra` field bisa ditampilkan sebagai JSON editor (misal pakai `@monaco-editor/react`) atau form key-value dinamis

---

### 4. Templates

```
┌──────────────────────────────────────────────────────────────┐
│  Templates                                  [+ Buat Template]│
├────────────────────────────────────────────────────────────  │
│  Filter: [Semua ▾]  [Publik]  [Milik Saya]                  │
├─────────────────────┬─────────────────────────────────────── │
│  [Preview Image]    │  Company Profile                       │
│                     │  Kategori: Business                    │
│                     │  3 pages • 8 sections                  │
│                     │  [Pakai Template]  [Detail]            │
├─────────────────────┼─────────────────────────────────────── │
│  [Preview Image]    │  Portfolio (MILIK SAYA) [Draft]        │
│                     │  Kategori: Creative                    │
│                     │  2 pages • 5 sections                  │
│                     │  [Edit]  [Publish ke Katalog]          │
└─────────────────────┴─────────────────────────────────────── │
```

**API calls:**
```
GET  /api/templates/?visibility=public   → template publik
GET  /api/templates/?visibility=private  → template milik saya
POST /api/templates/                     → buat template baru
POST /api/templates/{id}/publish/        → publish ke katalog global
DELETE /api/templates/{id}/publish/      → unpublish

POST /api/tenant/apply-template/         → terapkan template ke site
{ "template_id": "uuid", "overwrite": false }
```

**Flow "Pakai Template":**
```
1. User klik [Pakai Template]
2. Tampilkan modal konfirmasi:
   - Jika site sudah punya konten: "Ini akan menghapus semua halaman yang ada. Lanjutkan?"
   - Checkbox [Timpa konten yang ada] → sets overwrite=true
3. POST /api/tenant/apply-template/
4. Redirect ke /dashboard/pages untuk lihat halaman yang baru di-clone
```

---

### 5. Media Library (Files)

```
┌──────────────────────────────────────────────────────────────┐
│  Media Library                              [Upload File]    │
├─────────────────────────────────────────────────────────────┤
│  [🔍 Search]                    Filter: [Semua ▾] [Gambar]  │
├──────────┬──────────┬──────────┬──────────┬──────────────── │
│ [img]    │ [img]    │ [img]    │ [img]    │                 │
│ logo.png │ hero.jpg │ team.jpg │ bg.webp  │                 │
│ 45 KB    │ 120 KB   │ 89 KB    │ 210 KB   │                 │
│ [Copy URL][✕]                                               │
└──────────┴──────────┴──────────┴──────────┴──────────────── │
```

**Upload flow:**
```js
// 1. Init upload
const { data } = await api.post('/api/files/init-upload/', {
  filename: file.name,
  mime_type: file.type,
  size_bytes: file.size,
  owner_scope: 'org',
  visibility: 'public'
})

const { reference_id, multipart } = data
// multipart.upload_id = S3 multipart upload ID
// multipart.parts[0].presign_url = URL untuk PUT langsung ke S3

// 2. Upload tiap part langsung ke S3 (bypass server)
await fetch(multipart.parts[0].presign_url, {
  method: 'PUT',
  body: filePart,
  headers: { 'Content-Type': file.type }
})

// 3. Complete
await api.post(`/api/files/${reference_id}/complete/`, {
  parts: [{ part_number: 1, etag: response.headers.get('ETag') }]
})

// 4. Gunakan URL dari response sebagai image_url block
```

---

### 6. Domains

```
┌──────────────────────────────────────────────────────────────┐
│  Domains                                                     │
├──────────────────────────────────────────────────────────────┤
│  yapu.arnasite.id    [PRIMARY]                               │
│  yapu.com            [AKTIF]  [Hapus]                        │
├──────────────────────────────────────────────────────────────┤
│  [+ Tambah Domain]                                           │
│  Domain: [________________________]  [Tambahkan]            │
└──────────────────────────────────────────────────────────────┘
```

**API calls:**
```
GET    /api/domains/         → list domain
POST   /api/domains/         → tambah domain baru
DELETE /api/domains/{id}/    → hapus domain (primary tidak bisa dihapus)
```

---

### 7. Settings (Tenant)

```
┌──────────────────────────────────────────────────────────────┐
│  Tenant Settings                                             │
├──────────────────────────────────────────────────────────────┤
│  Nama Tampilan: [Yapu Store________________]                 │
│  Slug:          yapu  (tidak bisa diubah)                    │
│  Schema:        yapu  (tidak bisa diubah)                    │
│  Org ID:        uuid...  (dari Arna SSO)                     │
│  Dibuat:        14 April 2026                                │
│                                          [Simpan Perubahan]  │
└──────────────────────────────────────────────────────────────┘
```

**API calls:**
```
GET   /api/tenant/     → info tenant lengkap
PATCH /api/tenant/     → update nama
{ "name": "Nama Baru" }
```

---

## Public Site — Rendering Engine

Public site di-render dari data yang dikembalikan endpoint publik. Tidak memerlukan autentikasi.

### Entry Points

```
GET /api/public/site/           → daftar pages (untuk navigasi)
GET /api/public/site/{slug}/    → konten halaman lengkap
```

### Response Structure

```json
{
  "id": "uuid",
  "title": "Home",
  "slug": "home",
  "is_home": true,
  "meta_title": "Yapu Store - Belanja Mudah",
  "meta_description": "...",
  "sections": [
    {
      "id": "uuid",
      "type": "hero",
      "order": 1,
      "is_active": true,
      "blocks": [
        {
          "id": "uuid",
          "title": "Selamat Datang di Yapu",
          "subtitle": "Tagline keren",
          "description": "Deskripsi panjang...",
          "image_url": "https://storage.arnatech.id/...",
          "extra": { "cta_text": "Mulai Sekarang", "cta_url": "/contact" },
          "order": 1,
          "items": []
        }
      ]
    },
    {
      "id": "uuid",
      "type": "features",
      "order": 2,
      "blocks": [
        {
          "title": "Kenapa Kami",
          "items": [
            { "title": "Cepat",  "icon": "bolt",   "description": "..." },
            { "title": "Aman",   "icon": "shield",  "description": "..." }
          ]
        }
      ]
    }
  ]
}
```

### Next.js Page Renderer

```tsx
// app/[slug]/page.tsx
import { SECTION_MAP } from '@/components/sections'

export async function generateMetadata({ params }) {
  const page = await fetchPage(params.slug)
  return {
    title: page.meta_title || page.title,
    description: page.meta_description,
  }
}

export default async function PublicPage({ params }) {
  const page = await fetchPage(params.slug)

  return (
    <main>
      {page.sections
        .filter(s => s.is_active)
        .sort((a, b) => a.order - b.order)
        .map(section => {
          const Component = SECTION_MAP[section.type]
          if (!Component) return null
          return <Component key={section.id} blocks={section.blocks} />
        })}
    </main>
  )
}

async function fetchPage(slug: string) {
  const tenantDomain = process.env.TENANT_API_URL // e.g. https://yapu.arnasite.id
  const res = await fetch(`${tenantDomain}/api/public/site/${slug}/`, {
    next: { revalidate: 60 } // ISR: revalidate tiap 60 detik
  })
  if (!res.ok) notFound()
  return res.json()
}
```

---

## Section Type → Component Mapping

```ts
// components/sections/index.ts
export const SECTION_MAP: Record<string, React.ComponentType<SectionProps>> = {
  hero:        HeroSection,
  about:       AboutSection,
  features:    FeaturesSection,
  team:        TeamSection,
  gallery:     GallerySection,
  testimonial: TestimonialSection,
  pricing:     PricingSection,
  faq:         FaqSection,
  contact:     ContactSection,
  cta:         CtaSection,
  stats:       StatsSection,
}
```

### Pola Komponen

Semua section menerima `blocks` sebagai prop. Field `extra` digunakan untuk data yang tidak masuk ke field standar.

**HeroSection** — 1 block, tanpa items:
```tsx
function HeroSection({ blocks }: SectionProps) {
  const b = blocks[0]
  return (
    <section>
      {b.image_url && <img src={b.image_url} alt={b.title} />}
      <h1>{b.title}</h1>
      <p>{b.subtitle}</p>
      <p>{b.description}</p>
      {b.extra?.cta_text && (
        <a href={b.extra.cta_url}>{b.extra.cta_text}</a>
      )}
    </section>
  )
}
```

**FeaturesSection** — 1 block, banyak items:
```tsx
function FeaturesSection({ blocks }: SectionProps) {
  const b = blocks[0]
  return (
    <section>
      <h2>{b.title}</h2>
      <p>{b.description}</p>
      <div className="grid grid-cols-3 gap-6">
        {b.items.map(item => (
          <div key={item.id}>
            <Icon name={item.icon} />
            <h3>{item.title}</h3>
            <p>{item.description}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
```

**TeamSection** — banyak blocks (1 block = 1 anggota tim):
```tsx
function TeamSection({ blocks }: SectionProps) {
  return (
    <section>
      <div className="grid grid-cols-4 gap-4">
        {blocks.sort((a, b) => a.order - b.order).map(member => (
          <div key={member.id}>
            <img src={member.image_url} alt={member.title} />
            <h3>{member.title}</h3>       {/* nama */}
            <p>{member.subtitle}</p>      {/* jabatan */}
            <p>{member.description}</p>   {/* bio */}
            {/* extra: { linkedin: "...", twitter: "..." } */}
          </div>
        ))}
      </div>
    </section>
  )
}
```

**PricingSection** — banyak blocks (1 block = 1 tier), items = fitur:
```tsx
function PricingSection({ blocks }: SectionProps) {
  return (
    <section>
      <div className="grid grid-cols-3 gap-6">
        {blocks.map(tier => (
          <div key={tier.id} className={tier.extra?.is_popular ? 'ring-2' : ''}>
            {tier.extra?.badge_text && <span>{tier.extra.badge_text}</span>}
            <h3>{tier.title}</h3>           {/* nama tier */}
            <p>{tier.subtitle}</p>          {/* harga */}
            <p>{tier.description}</p>       {/* deskripsi */}
            <ul>
              {tier.items.map(feature => (
                <li key={feature.id}>{feature.title}</li>
              ))}
            </ul>
            <a href={tier.extra?.cta_url}>{tier.extra?.cta_text}</a>
          </div>
        ))}
      </div>
    </section>
  )
}
```

**FaqSection** — 1 block, items = Q&A:
```tsx
function FaqSection({ blocks }: SectionProps) {
  const b = blocks[0]
  return (
    <section>
      <h2>{b.title}</h2>
      <div>
        {b.items.map(item => (
          <details key={item.id}>
            <summary>{item.title}</summary>  {/* pertanyaan */}
            <p>{item.description}</p>        {/* jawaban */}
          </details>
        ))}
      </div>
    </section>
  )
}
```

### Convention `extra` per Section Type

| Section | Extra fields yang umum dipakai |
|---------|-------------------------------|
| `hero` | `cta_text`, `cta_url`, `bg_color`, `bg_image_url` |
| `features` | `layout: "grid"\|"list"`, `columns: 3` |
| `team` | `layout: "grid"\|"carousel"` |
| `pricing` | `is_popular: bool`, `badge_text`, `cta_text`, `cta_url`, `currency` |
| `testimonial` | `rating: 1-5`, `company`, `avatar_url` |
| `cta` | `cta_text`, `cta_url`, `bg_color`, `variant: "dark"\|"light"` |
| `contact` | `email`, `phone`, `maps_embed_url`, `show_form: bool` |

---

## File Upload Flow

```
┌─────────┐    POST /api/files/init-upload/    ┌─────────────┐
│   FE    │ ─────────────────────────────────► │  ArnaSite   │
│         │ ◄───────────────────────────────── │             │
│         │  { reference_id, multipart: {      │  (proxy ke  │
│         │    upload_id, parts: [{             │  Arna File  │
│         │      part_number: 1,               │  Manager)   │
│         │      presign_url: "https://s3..."  │             │
│         │    }]                              │             │
│         │  }}                               └─────────────┘
│         │
│         │    PUT presign_url (langsung ke S3)
│         │ ─────────────────────────────────► S3
│         │ ◄─────────────────────────────────
│         │  ETag header
│         │
│         │    POST /api/files/{id}/complete/
│         │ ─────────────────────────────────► ArnaSite
│         │ ◄─────────────────────────────────
│         │  { id, url, status: "active" }
└─────────┘
   Gunakan url sebagai image_url di block
```

---

## Error Handling

| HTTP | Artinya | Tindakan FE |
|------|---------|-------------|
| `400` | Validasi gagal | Tampilkan error per field dari `response.data` |
| `401` | Token invalid/expired | Refresh token atau redirect ke login |
| `403` | Tidak punya permission | Tampilkan pesan "Anda tidak memiliki akses" |
| `404` | Resource tidak ada | Tampilkan 404 page |
| `409` | Konflik (template sudah diterapkan, dll) | Tampilkan pesan konfirmasi dengan opsi overwrite |
| `502` | Arna File Manager tidak bisa dihubungi | Tampilkan "Upload gagal, coba lagi" |
| `500` | Server error | Log ke Sentry, tampilkan pesan umum |

**Error response format:**
```json
{ "error": "Pesan error dalam Bahasa Indonesia" }
// atau DRF standard:
{ "detail": "..." }
// atau validasi:
{ "field_name": ["Pesan error untuk field ini"] }
```

---

## Local Development Setup

```bash
# 1. Jalankan ArnaSite backend
cd arna_site
python manage.py runserver 8000

# 2. Tambah hosts (sekali saja)
# Windows: C:\Windows\System32\drivers\etc\hosts
# Linux/Mac: /etc/hosts
127.0.0.1   test.localhost
127.0.0.1   yapu.localhost

# 3. Akses Swagger untuk eksplorasi API
# Public API : http://localhost:8000/swagger/
# Tenant API : http://test.localhost:8000/swagger/
#              http://yapu.localhost:8000/swagger/

# 4. Set environment FE
NEXT_PUBLIC_TENANT_API_URL=http://yapu.localhost:8000
NEXT_PUBLIC_PUBLIC_API_URL=http://localhost:8000
```

**CORS:** Pastikan origin FE (misal `http://localhost:3000`) ada di `CORS_ALLOWED_ORIGINS` di `.env` ArnaSite.

---

## Catatan Penting

1. **Tenant context otomatis dari domain** — tidak perlu kirim tenant ID di request. Domain `yapu.localhost:8000` secara otomatis routing ke schema `yapu`.

2. **`section.type` bersifat string bebas** — ArnaSite tidak punya daftar enum hard-coded. FE yang mendefinisikan komponen apa yang di-render per type. Koordinasikan dengan backend/content editor type apa saja yang digunakan.

3. **`extra` field** — gunakan ini untuk data yang tidak masuk field standar. Definisikan schema-nya di FE dan dokumentasikan convention per section type.

4. **ISR / SSG untuk public site** — gunakan `next: { revalidate: 60 }` atau trigger revalidation via webhook setiap kali konten diupdate dari dashboard.

5. **Multi-page navigation** — `GET /api/public/site/` mengembalikan daftar semua halaman aktif. Gunakan ini untuk membangun navbar/sitemap publik.

---

## AI Copilot Integration (ChatGPT-like UX)

Dokumen ini menambahkan panduan FE untuk fitur `AI Site Copilot` (`/api/ai/*`) dengan pengalaman yang menyerupai antarmuka ChatGPT.

### Tujuan UX

- Memberi pengalaman brainstorming cepat seperti chat assistant modern.
- Menyediakan dua mode yang bisa dipilih user:
  - `chat_economy` (hemat token, text-first)
  - `multimodal_vision` (native vision untuk analisis screenshot/image)
- Menghasilkan draft terstruktur yang bisa di-review lalu publish.

### Endpoint yang Dipakai

Base: `https://{tenant-domain}`

```
POST /api/ai/sessions/
GET  /api/ai/sessions/
GET  /api/ai/sessions/{session_id}/
POST /api/ai/sessions/{session_id}/messages/
POST /api/ai/sessions/{session_id}/generate/
GET  /api/ai/sessions/{session_id}/drafts/
POST /api/ai/sessions/{session_id}/publish/
GET  /api/ai/sessions/{session_id}/fe-guide/
```

Header standar:
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

---

### Full FE Flow

#### 1) Create Session

User pilih mode kerja:
- Business mode: `template` atau `site`
- LLM mode: `chat_economy` atau `multimodal_vision`

```json
POST /api/ai/sessions/
{
  "mode": "template",
  "llm_mode": "multimodal_vision",
  "llm_model": "",
  "title": "Nusa Prima New Site"
}
```

#### 2) Send Message + Optional Images

User mengetik prompt, lalu attach referensi screenshot.

Catatan penting:
- Gunakan flow `/api/files/...` dulu untuk upload file.
- Setelah upload selesai, kirim URL hasil upload sebagai `attachments`.

```json
POST /api/ai/sessions/{id}/messages/
{
  "role": "user",
  "content": "Saya ingin style homepage seperti referensi ini, lebih clean dan trust-oriented.",
  "attachments": [
    {
      "type": "image",
      "url": "https://storage.arnatech.id/files/xxx.jpg",
      "mime_type": "image/jpeg",
      "caption": "Hero inspiration"
    }
  ]
}
```

Response akan berisi `assistant_reply` untuk melanjutkan brainstorming.

#### 3) Generate Draft

Saat user merasa diskusi cukup, klik tombol `Generate`:

```json
POST /api/ai/sessions/{id}/generate/
{}
```

- Jika mode `template`: hasil draft template + draft FE guide.
- Jika mode `site`: hasil draft konten website.

#### 4) Review Draft Panel

Load draft:

```
GET /api/ai/sessions/{id}/drafts/
```

Tampilkan:
- `template` draft JSON
- `site_content` draft JSON
- `fe_guide` draft markdown/json

#### 5) Publish

Template mode:
```json
POST /api/ai/sessions/{id}/publish/
{
  "template_draft_id": "<uuid>",
  "fe_guide_draft_id": "<uuid>"
}
```

Site mode:
```json
POST /api/ai/sessions/{id}/publish/
{
  "site_content_draft_id": "<uuid>",
  "overwrite": false
}
```

---

### ChatGPT-like Layout Recommendation

### Desktop Layout

Gunakan layout 3 kolom:

```
┌────────────────────┬──────────────────────────────────────────────┬─────────────────────────────┐
│ LEFT SIDEBAR       │ CHAT THREAD                                  │ RIGHT PANEL                 │
│                    │                                              │                             │
│ + New Session      │  Assistant/User message bubbles             │ Drafts                      │
│ Session list       │  Attachment previews                         │ - Template JSON             │
│ - title            │  Streaming-like response feel                │ - Site Content JSON         │
│ - mode badge       │                                              │ - FE Guide Markdown         │
│ - updated time     │  Composer (sticky bottom):                   │                             │
│                    │  [attach] [mode toggle] [send]              │ Publish CTA                 │
└────────────────────┴──────────────────────────────────────────────┴─────────────────────────────┘
```

### Mobile Layout

- Screen 1: chat thread + composer
- Screen 2 (drawer/bottom-sheet): session list
- Screen 3 (drawer/bottom-sheet): drafts & publish

---

### UI Components (recommended)

- `CopilotSessionSidebar`
  - list sessions + `New Session`
- `CopilotModeSwitcher`
  - segmented control: `Economy` / `Vision`
- `CopilotChatThread`
  - user/assistant bubbles
  - attachment thumbnail grid
- `CopilotComposer`
  - textarea autosize
  - image attach button
  - send button
- `CopilotDraftPanel`
  - tabs: `Template`, `Site`, `FE Guide`
  - JSON viewer + markdown viewer
- `CopilotPublishBar`
  - publish button + overwrite toggle (site mode)

---

### Interaction Details (agar terasa seperti ChatGPT)

1. **Sticky composer** di bawah viewport.
2. **Auto-scroll** ke message terbaru saat reply masuk.
3. **Keyboard-first**:
- Enter = send
- Shift+Enter = newline
4. **Message status**:
- `sending`, `sent`, `error`
5. **Attachment chips** sebelum send:
- thumbnail, filename, remove action
6. **Mode visibility**:
- tampilkan badge aktif: `Economy` / `Vision`
7. **Draft generation status**:
- idle -> generating -> ready -> failed

---

### Suggested FE State Model

Gunakan kombinasi:
- `TanStack Query` untuk server state (`sessions`, `messages`, `drafts`)
- `Zustand` untuk local UI state (`selectedSessionId`, `composerText`, `uploadQueue`, `panelOpen`)

Entity minimal:

```ts
type CopilotSession = {
  id: string
  mode: 'template' | 'site'
  llm_mode: 'chat_economy' | 'multimodal_vision'
  llm_model: string
  status: 'active' | 'generated' | 'published' | 'failed'
  title: string
  created_at: string
  updated_at: string
}
```

---

### Permission-aware UI

- Jika user hanya member (non admin/owner):
  - disable tombol write (`send`, `generate`, `publish`)
  - tampilkan label read-only.
- Jika admin/owner:
  - semua aksi aktif.

---

### Error Handling (AI-specific)

Tambahkan handling berikut:

| HTTP | Kasus | FE Action |
|------|------|-----------|
| `400` | schema invalid / publish invalid | tampilkan detail error di draft panel |
| `401` | token invalid/expired | refresh token / relogin |
| `403` | permission denied | tampilkan access denied |
| `404` | session/draft tidak ditemukan | redirect ke session list |
| `500` | server error | fallback toast + log Sentry |

---

### Practical UX Tips

1. Default mode saat create session: `chat_economy`.
2. Tampilkan tooltip:
- `Economy`: faster + cheaper
- `Vision`: better for screenshot analysis
3. Saat user attach image pertama, sarankan switch ke `Vision`.
4. Simpan drafts otomatis di panel kanan agar user tidak kehilangan context.
5. Beri CTA jelas setelah generate: `Review Draft` -> `Publish`.

