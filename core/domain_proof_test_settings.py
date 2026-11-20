# Hermetic no-DB settings: never import deployment .env/settings or real authentication keys.
SECRET_KEY = "synthetic-settings-only-not-a-receipt-key"
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "django_tenants", "core"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DATABASE_ROUTERS = ["django_tenants.routers.TenantSyncRouter"]
TENANT_MODEL = "core.Tenant"
TENANT_DOMAIN_MODEL = "core.Domain"
TENANT_APPS = ["core"]
SHARED_APPS = ["django_tenants", "core"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
ALLOWED_HOSTS = ["testserver"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
REST_FRAMEWORK = {"DEFAULT_AUTHENTICATION_CLASSES": [],
                  "UNAUTHENTICATED_USER": None}
SSO_JWT_ALGORITHM = "RS256"
SSO_JWT_PUBLIC_KEY_PATH = "/nonexistent-synthetic-key.pem"
ROOT_URLCONF = "core.domain_proof_test_urls"
