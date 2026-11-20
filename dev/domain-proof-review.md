# Domain ownership candidate — HOLD, no live activation
Baseline ardzix/arna_site main a4e66d20dcf915e874b0291117e0d6b063df6eb4. Website draft ardzix/arna-web PR2 head bcdd30e50e8977347d841f3c05b323931db7de75 remains unmerged/off.

## Why this candidate
Domain create accepted a client-selected active status; DomainDetailView.patch stamped verified_at on a status update. The normal API/admin paths now cannot grant verified authority that way. New custom domains and existing pending custom domains require matching ownership audit evidence at the public context/resolver gate. Previously active legacy domains are preserved explicitly by migration; this does not retrospectively prove their ownership.

## Supported evidence and proposed local receipt contract
Vercel documents GET https://api.vercel.com/v9/projects/{project}/domains/{domain}, including exact projectId/name/verified, and GET project exposes accountId. Source: https://vercel.com/docs/rest-api/projects/get-a-project-domain and https://vercel.com/docs/rest-api/projects/find-a-project-by-id-or-name .
The candidate uses authenticated fixed-host GETs only: no DNS write, no DNS checker, no Vercel verify/deploy mutation, and no fetch to a tenant-supplied hostname. Server-approved exact tenant UUID/org/hostname/project/team binding is required, along with Vercel verified=true, no branch/custom-environment/redirect and matching project account.
A public website/A record alone is not accepted as proof. Vercel authority attests domain use on that project; the server binding is the separate organization authorization decision and requires approval.

NEW candidate receipt, not an existing Vercel or ArnaSite protocol: HMAC-SHA256 with a dedicated >=32-byte receipt key, versioned salt, 120-second validity, exact domain ID/hostname, tenant/org/actor UUIDs, existing challenge hash/method, configured project/team and filtered evidence hash. Never signed using SECRET_KEY as fallback. Receipt contains public metadata but is a short-lived capability: do not log/store raw receipt.
Proof POST returns proof_observed_not_activated and does not save. Commit POST re-GETs provider evidence, then atomically locks tenant before domain, rechecks tenant/org/hostname/challenge/config/expiry/actor and consumes the challenge while adding audit and activation in one transaction. Network stays outside locks. Concurrent second commit must fail after the first changes pending state/token; actual PostgreSQL concurrency is a required unrun gate, not proven by mocked locks.
Provider can change immediately after a read: no distributed transaction with Vercel is claimed. Receipts are short-lived and commit refreshes evidence; continuous domain revocation remains a separate operational policy.

## Candidate routes and authorization
Under existing /api/domains/ mount:
POST <id>/ownership/proof/ with empty JSON.
POST <id>/ownership/commit/ with {receipt: ...}, no other fields.
Explicit existing ArnaJWTAuthentication + authenticated exact-org site_admin/owner, active nonpublic tenant; no legacy schema fallback, no browser receipt-only authority. Five requests/min/user+org. No tenant creation or ownership change. Existing JWT role revocation/cache semantics remain an external auth prerequisite; these tests do not validate real JWT/SSO.
Configuration defaults disabled when absent:
DOMAIN_VERCEL_PROOF_ENABLED = False
DOMAIN_VERCEL_PROOF_BINDINGS = {}  # tenant UUID -> exact organization_id, host, project_id, team_id
DOMAIN_VERCEL_API_TOKEN = ""       # obtain least-privilege via approved secret manager; never browser
DOMAIN_VERCEL_RECEIPT_KEY = ""     # dedicated managed secret, rotation invalidates pending receipts
No real values are included or installed. Missing binding/key/token cannot activate anything.
Tenant85 already exists, UUID10996862-26be-4c7a-8a05-acb814f77975, org25c1bf82-5eac-4507-a5d7-b1e271fdbb9f. Its exact approved Vercel project/team IDs and provider state are NOT verified here; no live connector/credentials available. Never invent them.

## DB/admin/rollback boundaries
Migration0008 only marks existing pending custom domains proof-required; defaults new domains to proof-required; adds audit model with hashes/public identity. Do not run it on live without preflight, backup/rollback review and authorization.
Audit-protected domains need matching current hostname/tenant/org/method evidence; bare status/verified_at changes do not satisfy routing. A privileged SQL writer can alter all authority tables: application code cannot defend against a DB superuser forging/mutating both records and audit. No DB override is an approved procedure; DB role restrictions/operational security require separate approval.
DomainAdmin verification fields are read-only; audit is not registered for admin editing. Deletion of a proved domain is protected while audit exists; decide retention/archive flow before production adoption.
Rollback first disables candidate proof feature and keeps website chat off; retain forward DB schema/audit and proof-required admission until explicit reviewed rollback. Reverting to the old vulnerable status API or dropping audit records is not a safe rollback.

## Tests and remaining release gates
CI uses isolated no-env test settings, binary-only pinned subset, synthetic provider responses, mocked row locks and no database access. It tests signature/TTL, actor/tenant/config/challenge races, provider redirect/size/errors, no status-only context admission, strict owner permissions, disabled gate and replay.
No live Vercel/CRM/SSO calls, OTP, customer records, outbound messages or provider credentials in tests.
Still required before any deployment/activation: independent security review and explicit approval of provider trust, scoped credentials/key and tenant/project/team mapping; real PostgreSQL16 migrations/rollback and competing commit races; deployed image/source provenance; actual provider read-only evidence; approved isolated live E2E with egress disabled/mocked for OTP/messages. Current CRM source intake still needs verified customer for chat; name/email/message no-OTP form remains503. Do not substitute customer start to capture a contact enquiry.
Website remains one responsive app; no SEO scope change.
