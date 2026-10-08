# Public website routing context

`GET /api/v1/website/context/?host=business.example.com` supplies routing
metadata for the public Arna CRM website gateway. It is available on both the
central public host and tenant URL configurations. Existing domain resolver
routes remain compatible; `domains/website-context/` is a routing adapter.

Only exact lowercase DNS hostnames on active, verified frontend domains of an
active tenant are accepted. Pending/inactive domains, backend API domains,
unknown hosts, ports and URLs cannot obtain a website context. The endpoint
queries ArnaSite's own public domain/tenant tables and emits the stable UUID
`tenant.public_id` and validated `sso_organization_id`, never the legacy numeric
tenant primary key or shared schema name.

Successful public response:

```json
{
  "host": "business.example.com",
  "origin": "https://business.example.com",
  "organization_id": "11111111-1111-4111-8111-111111111111",
  "tenant_id": "22222222-2222-4222-8222-222222222222"
}
```

These IDs establish domain routing only. They grant no org membership, product
entitlement, service authentication, or customer identity. CRM must validate
its configured ArnaSite HTTPS origin, check Commerce entitlements and authenticate
the customer with SSO before opening conversations or running AI. No secret is
returned or stored in frontend tenant configuration. Both canonical and alias
domains use the owning tenant; activating another verified frontend domain
requires no per-domain gateway secret or frontend deployment.

All responses use no-store. Errors use the error/detail/request_id envelope.
The isolated `core.test_website_context.WebsiteContextTest` checks alias UUID
identity, required domain/tenant conditions, invalid hosts and invalid IDs.
