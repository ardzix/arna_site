# AI Helper Blueprint (ArnaSite)

## Nama Fitur
`AI Site Copilot`

Mode:
1. `Template Builder Copilot`
2. `Website Content Copilot`

## Tujuan
- Membantu user brainstorming menggunakan chat multimodal (text + image).
- Output akhir berupa structured CMS data (bukan HTML mentah).
- Untuk mode template, generate juga `FE_GUIDE.md` untuk panduan implementasi frontend.

## High-Level Flow
1. User membuka Copilot di dashboard tenant.
2. User memilih mode:
- `Create Template`
- `Create Website`
3. User chat prompt + upload gambar referensi.
4. LLM melakukan iterasi tanya-jawab (style, brand, target audience, CTA, struktur section, tone copywriting).
5. User klik `Generate`.
6. Backend menjalankan pipeline:
- summarize brief
- generate draft struktur JSON terstandar
- validate schema
- tampilkan preview + editable draft
7. User klik `Publish`:
- Mode template -> simpan ke `Template + TemplatePage + ...` + generate `FE_GUIDE.md`
- Mode website -> simpan ke `Page + Section + ...` pada tenant aktif

## Output yang Di-generate

### A) Template Mode
- Structured template data:
  - pages, sections, blocks, items
  - convention `extra` per section type
- `FE_GUIDE.md` berisi:
  - daftar section yang dipakai
  - mapping prop per section
  - contoh JSON payload
  - guidance layout, responsive, spacing, CTA behavior
  - daftar asset/image requirement
  - optional accessibility checklist

### B) Website Mode
- Konten final berdasarkan template terpilih:
  - copywriting (title/subtitle/description)
  - list items
  - CTA text/url
  - image slots (placeholder/URL)
- Optional auto-publish flag (atau tetap manual publish).

## Arsitektur Teknis (Ringkas)
1. **Copilot Session Service**
- Menyimpan chat history, state, selected template, uploaded references.

2. **Multimodal LLM Adapter**
- Provider-agnostic interface (fase awal: DeepSeek).
- Method utama:
  - `brainstorm_reply()`
  - `generate_template_json()`
  - `generate_site_content_json()`
  - `generate_fe_guide_md()`

3. **Schema Validator Layer**
- Validasi ketat terhadap JSON schema internal.
- Opsi auto-repair pass jika format output belum valid.

4. **Draft-to-Publish Pipeline**
- Draft disimpan dulu (`status=draft_ai`).
- Publish baru commit ke model production.

5. **Asset Intake**
- Gambar user di-upload ke storage service ArnaSite, URL diberikan ke model sebagai reference.

## Usulan Model Data Baru
- `AICopilotSession`
  - `id`, `tenant`, `mode`, `status`, `created_by`, `current_step`, timestamps
- `AICopilotMessage`
  - `session`, `role`, `content`, `attachments[]`, `metadata`
- `AIGenerationDraft`
  - `session`, `draft_type(template|site|fe_guide)`, `payload_json`, `markdown_text`, `validation_report`, `is_selected`
- `AIPromptPreset`
  - default system prompts per mode/language/style

## Usulan Endpoint API
- `POST /api/ai/sessions/`
- `POST /api/ai/sessions/{id}/messages/`
- `POST /api/ai/sessions/{id}/attachments/`
- `POST /api/ai/sessions/{id}/generate/`
- `GET  /api/ai/sessions/{id}/drafts/`
- `POST /api/ai/sessions/{id}/publish/`
- `GET  /api/ai/sessions/{id}/fe-guide/` (template mode)

## Guardrails Penting
- LLM tidak menulis langsung ke production DB tanpa review draft.
- Batasi jumlah page/section agar output tetap manageable.
- Semua hasil AI wajib lolos validator schema.
- Simpan provenance: prompt, model version, timestamp.
- Terapkan PII/content safety filter sebelum publish.

## MVP Scope (Realistis)
1. Brainstorm multimodal dari awal (text + image upload reference).
2. Generate draft template JSON + `FE_GUIDE.md`.
3. Generate draft website content dari template terpilih.
4. Manual review + publish.
5. Basic audit log.

## Next Steps yang Disarankan
1. Definisikan JSON schema final (template + content + FE guide sections).
2. Rancang API contract + DB migration plan untuk MVP.
3. Implement service `LLM Adapter` provider-agnostic (DeepSeek sebagai provider pertama).
