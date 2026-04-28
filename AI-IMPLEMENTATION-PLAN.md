# AI Copilot Implementation Plan (ArnaSite)

Dokumen ini menjelaskan bagaimana fitur `AI Site Copilot` akan diimplementasikan di project ArnaSite sebelum coding dimulai.

## 1. App Baru: `ai_helper`
Buat app Django baru khusus domain AI.

Isi utama app:
- `models.py`: session, message, attachment, draft
- `serializers.py`
- `views.py`
- `urls.py`
- `services.py` (orchestrator pipeline)
- `validators.py` (JSON schema validation)
- `llm_adapters/deepseek.py` (provider adapter pertama)

Alasan:
- Memisahkan concern AI dari `core/sites/storage`
- Memudahkan iterasi provider LLM tanpa mengganggu CMS utama

## 2. Data Model (Tenant Scoped)
Semua data Copilot disimpan di tenant schema (masuk `TENANT_APPS`).

### `AICopilotSession`
- `id` (UUID)
- `mode` (`template`, `site`)
- `status` (`active`, `generated`, `published`, `failed`)
- `llm_mode` (`chat_economy`, `multimodal_vision`)
- `llm_model` (optional per-session override)
- `created_by_user_id`
- `created_by_email`
- `selected_template_id` (nullable)
- `context_summary` (ringkasan brainstorm)
- timestamps

### `AICopilotMessage`
- `id`
- `session` (FK)
- `role` (`user`, `assistant`, `system`)
- `content`
- `seq` (urutan pesan)
- timestamps

### `AICopilotAttachment`
- `id`
- `message` (FK)
- `url`
- `mime_type`
- `caption` (nullable)

### `AIGenerationDraft`
- `id`
- `session` (FK)
- `draft_type` (`template`, `site_content`, `fe_guide`)
- `payload_json` (JSON output)
- `markdown_text` (khusus FE guide)
- `validation_report_json`
- `is_selected`
- `version`
- timestamps

## 3. Endpoint API (`/api/ai/...`)
Tambahkan route di tenant URL config:
- `POST /api/ai/sessions/`
- `GET /api/ai/sessions/{id}/`
- `POST /api/ai/sessions/{id}/messages/`
- `POST /api/ai/sessions/{id}/attachments/`
- `POST /api/ai/sessions/{id}/generate/`
- `GET /api/ai/sessions/{id}/drafts/`
- `POST /api/ai/sessions/{id}/publish/`
- `GET /api/ai/sessions/{id}/fe-guide/`

Permission:
- Read: `IsTenantMember`
- Write/generate/publish: `IsTenantAdmin | IsTenantOwner`

## 4. Image Flow di MVP (Included)
Image tetap masuk MVP menggunakan pipeline storage yang sudah ada:
1. FE upload file ke endpoint existing `/api/files/...`
2. FE simpan URL file hasil upload
3. FE kirim URL itu sebagai `attachments` pada message Copilot
4. Backend mengirim URL + caption ke LLM adapter sebagai konteks multimodal

Keuntungan:
- Reuse storage service existing
- Tidak perlu membuat upload infra baru

## 5. LLM Adapter Layer (DeepSeek First)
Buat interface adapter agar provider-agnostic.

Method minimum:
- `brainstorm_reply(messages, attachments, mode)`
- `generate_template_draft(session_context)`
- `generate_site_content_draft(session_context, template_id)`
- `generate_fe_guide(template_draft)`

Implementasi awal: `DeepSeekAdapter`.
Semua call LLM lewat service layer, bukan langsung dari view.

Mode behavior:
- `chat_economy`: attachments flattened as text reference to reduce token usage.
- `multimodal_vision`: attachments sent as native `image_url` content blocks.

## 6. Schema Validation Pipeline
Gunakan schema yang sudah ada di folder `ai_schemas/`:
- `template.schema.json`
- `site-content.schema.json`
- `fe-guide.schema.json`
- `copilot-message.schema.json`

Alur validasi:
1. Parse output LLM
2. Validate terhadap schema target
3. Jika invalid -> auto-repair pass 1 kali
4. Simpan draft + validation report
5. Hanya draft valid yang boleh dipublish

## 7. Publish Pipeline

### Mode Template
- Buat record `Template` (`is_published=false`)
- Map payload ke:
  - `TemplatePage`
  - `TemplateSection`
  - `TemplateBlock`
  - `TemplateListItem`
- Simpan FE guide markdown di `AIGenerationDraft(draft_type='fe_guide')`

### Mode Website
- Wajib ada `selected_template_id`
- Map payload ke:
  - `Page`
  - `Section`
  - `ContentBlock`
  - `ListItem`
- Support `overwrite` opsional (default `false`)

## 8. Guardrails
- Tidak ada write langsung ke production tanpa draft
- Batasi ukuran output (max page/section/block/item)
- Timeout/retry terkontrol untuk call LLM
- Simpan audit metadata: provider, model, latency, token usage, timestamp
- Sanitasi markdown output

## 9. Testing Strategy
- Unit test: validator, mapper publish, service orchestration
- Integration test: endpoint generate/publish (LLM dimock)
- Permission test: member vs admin/owner
- Regression test: draft invalid tidak bisa publish

## 10. Rollout Plan
1. **Phase 1**: session + chat + generate draft (tanpa publish)
2. **Phase 2**: publish template/site
3. **Phase 3**: prompt preset tuning + UX enhancement

## 11. Implementasi Pertama yang Direkomendasikan
Jika disetujui, urutan coding:
1. Scaffold app `ai_helper` + model + migration
2. Endpoint minimal: `sessions`, `messages`, `generate (draft-only)`
3. Integrasi validator schema + DeepSeek adapter mockable
4. Baru lanjut `publish` pipeline
