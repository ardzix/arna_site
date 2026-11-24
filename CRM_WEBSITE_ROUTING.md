# Website chat destination

By default, the public website context sends chat to the tenant that owns the verified domain. An operator may explicitly select another active CRM tenant in the same organization using `Domain.crm_tenant`. This changes only the CRM context, not `Domain.tenant`, CMS content, domain verification, subscriptions or historical conversations.

Use the owning ArnaSite management command, supplying immutable public UUIDs:

```sh
python manage.py set_website_crm_tenant \
  --organization ORG_UUID --website-tenant WEBSITE_OWNER_UUID \
  --expected-current-tenant CURRENT_CRM_UUID --target-tenant NEW_CRM_UUID \
  --host example.com --host www.example.com
```

This validates all hostnames and destinations and prints the planned bindings. Add `--apply` to commit them atomically. Repeating the same operation is idempotent. To return to the website owner, use `--clear` instead of `--target-tenant`, with the expected current destination. Cross-organization, inactive, unverified, missing or concurrently changed bindings fail without partial updates. The public resolver also fails closed for invalid destinations even if an operator bypassed model validation.

Existing CRM records keep their immutable tenant ownership. Old customer sessions are tenant-bound and are not reassigned; visitors may need to verify their number again after the routing cache expires (the CRM cache is bounded to at most 30 seconds). New conversations use the destination tenant's knowledge, support policy and channels. This command does not copy knowledge or history, change AI mode, send messages or run a backfill.
