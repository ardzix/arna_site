class SSOUser:
    """
    Lightweight user proxy populated from JWT claims.

    ✅ Stores ONLY primitive types (str, uuid str).
    ❌ Never store a live Django ORM instance here.
    Reason: Redis caches via pickle. Pickling a Django model instance
    (e.g. Tenant) either fails or returns stale DB state on unpickle,
    causing DatabaseError on the next request.
    """
    def __init__(self, user_id, email, org_id, tenant_schema, tenant_name, roles=None, permissions=None, is_owner=False):
        self.id = user_id
        self.email = email
        self.org_id = org_id
        self.tenant_schema = tenant_schema   # str — safe to pickle
        self.tenant_name = tenant_name       # str — safe to pickle
        self.roles = roles or []
        self.permissions = permissions or []
        self.is_owner = is_owner
        self.is_authenticated = True
        self.is_anonymous = False

    def __str__(self):
        return self.email
