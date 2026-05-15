# AI Copilot for ArnaSite

This document describes the implemented `ai_helper` module for AI-assisted template and website generation.

## Scope
The current implementation provides:
- Tenant-scoped AI sessions
- Multimodal brainstorming messages (text + image URLs)
- Draft generation for:
  - Template structure
  - Website content structure
  - Frontend guide metadata + markdown
- JSON Schema validation before publish
- Publish pipeline into existing ArnaSite models
- Runtime-selectable LLM mode:
  - `chat_economy` (text-first, token efficient)
  - `multimodal_vision` (native image_url input)

## App Structure
`ai_helper/`
- `models.py` — session, messages, attachments, drafts
- `serializers.py` — request/response serializers
- `views.py` — API endpoints
- `services.py` — orchestration and publish mapping
- `validators.py` — JSON Schema validation layer
- `llm_adapters/deepseek.py` — DeepSeek adapter (with fallback mode)
- `urls.py` — endpoint routes

## Data Model

### `AICopilotSession`
Represents one assistant workflow context.
- mode: `template` or `site`
- status: `active`, `generated`, `published`, `failed`
- llm_mode: `chat_economy` or `multimodal_vision`
- llm_model: optional per-session model override (default: `deepseek-chat`)
- template_id: nullable (default: `null`), only required for `site` mode generation

### `AICopilotMessage`
Stores chat messages for the session.
- role: `user`, `assistant`, `system`
- seq keeps deterministic order

### `AICopilotAttachment`
Stores image references associated with one message.
- type currently fixed to `image`
- URL points to uploaded file (reuse `/api/files/...` pipeline)

### `AIGenerationDraft`
Stores structured drafts produced by generation.
- draft_type: `template`, `site_content`, `fe_guide`
- payload_json and optional markdown_text
- validation_report_json for schema checks

## Endpoints
All endpoints are under tenant domain:
`/api/ai/`

1. `POST /api/ai/sessions/`
2. `GET /api/ai/template-options/`
3. `GET /api/ai/sessions/`
4. `GET /api/ai/sessions/{session_id}/`
5. `POST /api/ai/sessions/{session_id}/messages/`
6. `POST /api/ai/sessions/{session_id}/generate/`
7. `GET /api/ai/sessions/{session_id}/drafts/`
8. `GET /api/ai/sessions/{session_id}/template-draft/`
9. `GET /api/ai/sessions/{session_id}/site-content-draft/`
10. `GET /api/ai/sessions/{session_id}/fe-guide/`
11. `POST /api/ai/sessions/{session_id}/publish/`
12. `GET /api/ai/jobs/{job_id}/status/`

These endpoints are also documented in tenant Swagger (`/swagger/`) via `drf-yasg`.

`GET /api/ai/sessions/` is optimized for sidebar usage:
- no full `messages` array
- includes lightweight `subtitle` from last assistant message (truncated)
- supports load-more pagination via query params:
  - `limit` (default `20`, max `100`)
  - `offset` (default `0`)
- returns:
  - `items` (session rows)
  - `has_more` (boolean)
  - `next_offset` (null when end reached)
  - `total`

`GET /api/ai/template-options/` supports:
- `limit`, `offset` pagination
- `search` filter
- `selected_only=true` to return selected template drafts only

## Permissions
- Read operations: `IsAuthenticated + IsTenantMember`
- Write/generate/publish: `IsAuthenticated + IsTenantMember + (IsTenantAdmin or IsTenantOwner)`

## Environment Variables
Add in `.env`:
- `DEEPSEEK_BASE_URL` (default: `https://api.deepseek.com`)
- `DEEPSEEK_API_KEY` (empty means local fallback mode)
- `DEEPSEEK_MODEL` (default: `deepseek-chat`)
- `DEEPSEEK_VISION_MODEL` (optional; used for `multimodal_vision`)
- `Q_CLUSTER_WORKERS` (default: `2`)
- `Q_CLUSTER_TIMEOUT` (default: `180`)
- `Q_CLUSTER_RETRY` (default: `240`)
- `Q_CLUSTER_QUEUE_LIMIT` (default: `500`)
- `Q_CLUSTER_BULK` (default: `10`)

## Schema Validation
Validation uses files in `ai_schemas/`:
- `template.schema.json`
- `site-content.schema.json`
- `fe-guide.schema.json`
- `copilot-message.schema.json`

The validator uses `jsonschema` (added to `requirements.txt`).

## Generation Flow

### Template Mode
1. User creates session with `mode=template`
2. User sends one or more messages with optional image attachments
3. `generate` produces:
- template draft JSON
- FE guide draft JSON + markdown
  - FE guide is focused on frontend implementation guidance (component architecture, HTML semantics, responsive UX, theming), not business copy content
4. User publishes selected drafts
5. Backend writes into:
- `Template`
- `TemplatePage`
- `TemplateSection`
- `TemplateBlock`
- `TemplateListItem`

### Site Mode
1. User creates session with `mode=site` and `template_id`
2. User sends messages + references
3. `generate` produces site content draft JSON
4. User publishes draft
5. Backend writes into:
- `Page`
- `Section`
- `ContentBlock`
- `ListItem`

## Example Requests

### Create Session (Template)
```http
POST /api/ai/sessions/
Content-Type: application/json
Authorization: Bearer <token>

{
  "mode": "template",
  "llm_mode": "chat_economy",
  "llm_model": "deepseek-chat",
  "template_id": null,
  "title": "Modern Logistics Template"
}
```

Request fields:
- `mode`: `template` | `site`
- `llm_mode`: `chat_economy` | `multimodal_vision` (optional, default `chat_economy`)
- `llm_model`: optional explicit model override (default `deepseek-chat`)
- `template_id`: optional, default `null`; required only when you generate in `site` mode

### Add Message with Image
```http
POST /api/ai/sessions/{session_id}/messages/
Content-Type: application/json
Authorization: Bearer <token>

{
  "role": "user",
  "content": "Build a clean logistics template with trust-focused hero and pricing.",
  "attachments": [
    {
      "type": "image",
      "url": "https://storage.arnatech.id/files/abc.jpg",
      "mime_type": "image/jpeg",
      "caption": "Reference homepage look"
    }
  ]
}
```

Response (async):
```json
{
  "status": "asking",
  "job_id": "uuid",
  "check_status_url": "/api/ai/jobs/uuid/status/"
}
```

When job status is `done`, `result_json` contains:
```json
{
  "assistant_reply": "..."
}
```

### Create Session with Vision Mode
```http
POST /api/ai/sessions/
Content-Type: application/json
Authorization: Bearer <token>

{
  "mode": "template",
  "llm_mode": "multimodal_vision",
  "llm_model": "",
  "title": "Energy Brand Template"
}
```

### Generate Drafts
```http
POST /api/ai/sessions/{session_id}/generate/
Content-Type: application/json
Authorization: Bearer <token>

{}
```

Response (async):
```json
{
  "status": "asking",
  "job_id": "uuid",
  "check_status_url": "/api/ai/jobs/uuid/status/"
}
```

### Publish Template Draft
```http
POST /api/ai/sessions/{session_id}/publish/
Content-Type: application/json
Authorization: Bearer <token>

{
  "template_draft_id": "<uuid>",
  "fe_guide_draft_id": "<uuid>"
}
```

## Fallback Mode Behavior
If `DEEPSEEK_API_KEY` is empty:
- The adapter generates deterministic mock drafts.
- This allows API and publish pipeline testing without external LLM calls.

## Operational Notes
- Run worker process for async jobs:
  - `python manage.py qcluster`
- Use `/api/files/...` first to upload image assets, then pass resulting URLs in Copilot attachments.
- Keep prompt context concise; service truncates context to avoid oversized payloads.
- Publish is blocked if schema validation fails.
- In `chat_economy`, image references are flattened to text.
- In `multimodal_vision`, attachments are sent as native `image_url` message parts.
- Brainstorm replies are guardrailed to requirement discussion only:
  - no HTML/code blocks
  - no implementation snippets
  - no full template JSON in chat phase
  - simple Bahasa Indonesia for business users
  - structured output is generated only at `POST /generate/`
- `message`, `generate`, and `publish` are asynchronous:
  - `status=asking` when queued
  - `status=thinking` while worker runs
  - `status=done` when finished, result available in job status endpoint
  - `status=failed` when execution fails, error included in job payload

## Current Limitations
- No prompt preset management model yet.
- No token/latency analytics persistence yet.

## Recommended Next Enhancements
1. Add retry/backoff policy per operation (message/generate/publish).
2. Add auto-repair pass on invalid JSON output.
3. Add configurable prompt presets per industry.
4. Add richer FE guide markdown templates.
