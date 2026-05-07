# ArnaSite Frontend Integration Guide

## Objective

This guide helps ArnaSite frontend developers integrate package selection and purchase UX with Arna Commerce, so users can:
- register and start with Free,
- upgrade to Premium,
- get entitlement-based features applied immediately.

## What FE Should and Should Not Do

- FE should:
  - show package options and pricing
  - trigger backend APIs for order and payment actions
  - redirect user to hosted payment page
  - refresh subscription/entitlement state after payment
- FE should not:
  - call Xendit with secret keys
  - enforce final limits purely on client side

## Required UX Flows

## 1. Package Selection Screen

Display at least:
- Free
- Premium Monthly (`IDR 500,000`)

Feature matrix should map from entitlement semantics:
- max websites
- max templates
- max pages per template
- AI monthly calls
- custom domain availability

## 2. New User / New Organization Onboarding

Expected behavior:
1. User completes registration/login.
2. Organization context is available.
3. Backend activates Free package for that organization.
4. FE fetches current package and entitlement summary for rendering.

## 3. Upgrade to Premium

User interaction:
1. Click Upgrade.
2. FE calls ArnaSite backend endpoint (not Commerce directly from browser in public clients).
3. Backend creates order, submits order, and creates payment session.
4. FE receives Xendit checkout URL and redirects user.

## 4. Post-payment Return

After success redirect:
1. Show "processing payment" state.
2. Poll backend subscription status and entitlement summary.
3. Switch UI state to Premium once subscription is active and entitlement reflects premium values.

## API Contracts FE Usually Needs (via ArnaSite backend)

Current implemented backend contracts:

### Root/Public domain (`https://site.arnatech.id`)

- `GET /tenants/`
  - list tenant(s) for current logged-in user/org (Bearer JWT required)
- `POST /tenants/register/`
  - create tenant
  - defaults to shared tenancy for free/pro
  - bootstrap free package in Commerce (best-effort)

### Tenant domain (`https://{tenant-domain}`)

- `GET /api/tenant/`
  - current tenant profile
- `GET /api/tenant/entitlements/runtime/`
  - runtime entitlement summary (cached)
- `POST /api/tenant/checkout/premium/`
  - create premium checkout flow (order -> submit -> create payment)
  - returns payment session payload/URL from Commerce

### AI Copilot (tenant domain)

- `GET /api/ai/sessions/?limit={n}&offset={n}`
  - lightweight sidebar list, sorted newest first
  - returns `{ items, has_more, next_offset, total }`
- `POST /api/ai/sessions/`
  - create AI session
- `POST /api/ai/sessions/{session_id}/messages/`
  - async brainstorm message
- `POST /api/ai/sessions/{session_id}/generate/`
  - async draft generation
- `POST /api/ai/sessions/{session_id}/publish/`
  - async publish
- `GET /api/ai/jobs/{job_id}/status/`
  - poll async status (`asking|thinking|done|failed`)
- `GET /api/ai/sessions/{session_id}/template-draft/`
- `GET /api/ai/sessions/{session_id}/site-content-draft/`
- `GET /api/ai/sessions/{session_id}/fe-guide/`

If calling Commerce directly in trusted internal apps, reference:
- `POST /api/v1/orders/`
- `POST /api/v1/orders/{id}/submit/`
- `POST /api/v1/orders/{id}/create-payment/`
- `GET /api/v1/entitlements/runtime/`

## Entitlement-driven UI Behavior

Render UI from entitlement values instead of hardcoded plan names.

Keys to consume:
- `arnasite.max_websites`
- `arnasite.max_templates`
- `arnasite.max_pages_per_template`
- `arnasite.ai_generator.monthly_calls`
- `arnasite.custom_domain.enabled`

Examples:
- Disable "Add Website" button when usage reaches `max_websites`.
- Show remaining AI calls as:
  - `remaining = monthly_calls_limit - current_month_usage`
- Hide custom-domain controls when value is `false`.

For ArnaSite, consume entitlements from:
- `GET /api/tenant/entitlements/runtime/`
  - response includes flat map in `entitlements` object.

## Recommended FE States

- `loading_catalog`
- `loading_subscription`
- `payment_redirect_pending`
- `payment_processing`
- `subscription_active_free`
- `subscription_active_premium`
- `payment_failed`

## Error Handling Suggestions

- If upgrade request fails:
  - show actionable error and allow retry
- If payment succeeds but entitlement not updated yet:
  - show pending sync state and retry fetch
- If entitlement fetch fails:
  - fallback to last known state and prompt refresh
- For async AI operations:
  - always poll `check_status_url` until terminal status
  - handle `failed` by showing `error` from job payload
  - do not assume immediate assistant reply or draft availability

## Security Notes

- Always send Bearer token from authenticated session.
- Do not expose Xendit secret key in FE.
- Treat entitlements as server-authoritative; FE should reflect, not decide.

## Practical FE Checklist

1. Build package comparison UI using entitlement semantics from runtime endpoint.
2. Use `GET /tenants/` on root domain to resolve tenant/domain for logged-in org.
3. Implement upgrade CTA via `POST /api/tenant/checkout/premium/` and redirect to checkout URL.
4. Implement post-payment polling using entitlement runtime endpoint until premium values appear.
5. Implement AI session sidebar with load-more (`limit/offset`) and `next_offset`.
6. Implement async AI job polling for message/generate/publish operations.
7. Gate feature visibility using entitlement summary from backend.
8. Display usage meters (AI calls, templates/pages) from backend counters.
