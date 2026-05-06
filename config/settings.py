import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-default-key')
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

SHARED_APPS = (
    'django_tenants',
    'core',
    'authentication',
    'django_q',

    'rest_framework',
    'drf_yasg',
    'corsheaders',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
)

TENANT_APPS = (
    'sites',
    'storage',
    'ai_helper',

    'django.contrib.contenttypes',
)

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',  # MUST be first
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
PUBLIC_SCHEMA_URLCONF = 'config.public_urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': os.getenv('DB_NAME', 'arna_site'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)

TENANT_MODEL = "core.Tenant"
TENANT_DOMAIN_MODEL = "core.Domain"

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'authentication.jwt_backends.ArnaJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'authentication.permissions.IsTenantMember',
    ],
}

# Redis — used for JWT decode cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.getenv("REDIS_URL", "redis://localhost:6379/1"),
    }
}

# Arna Storage integration
ARNA_STORAGE_BASE_URL = os.getenv('ARNA_STORAGE_BASE_URL', 'https://storage.arnatech.id')
# Arna Commerce integration
ARNA_COMMERCE_BASE_URL = os.getenv('ARNA_COMMERCE_BASE_URL', 'https://product.arnatech.id/api/v1')
ARNA_COMMERCE_PRODUCT_CODE = os.getenv('ARNA_COMMERCE_PRODUCT_CODE', 'arna-site')
ARNA_COMMERCE_FREE_PLAN_CODE = os.getenv('ARNA_COMMERCE_FREE_PLAN_CODE', 'arna-site-free')
ARNA_COMMERCE_PREMIUM_PLAN_CODE = os.getenv('ARNA_COMMERCE_PREMIUM_PLAN_CODE', 'arna-site-premium-monthly')
ARNA_COMMERCE_ENTITLEMENT_KEY_PREFIX = os.getenv('ARNA_COMMERCE_ENTITLEMENT_KEY_PREFIX', 'arnasite.')
ARNA_COMMERCE_HTTP_TIMEOUT = int(os.getenv('ARNA_COMMERCE_HTTP_TIMEOUT', '20'))
ARNA_COMMERCE_ENTITLEMENT_CACHE_TTL = int(os.getenv('ARNA_COMMERCE_ENTITLEMENT_CACHE_TTL', '300'))
ARNA_COMMERCE_BOOTSTRAP_FREE_ON_REGISTER = os.getenv(
    'ARNA_COMMERCE_BOOTSTRAP_FREE_ON_REGISTER', 'True'
).lower() in ('true', '1', 'yes')
ARNA_COMMERCE_FREE_PAYMENT_METHOD = os.getenv('ARNA_COMMERCE_FREE_PAYMENT_METHOD', 'invoice')
ARNA_COMMERCE_PREMIUM_PAYMENT_METHOD = os.getenv('ARNA_COMMERCE_PREMIUM_PAYMENT_METHOD', 'pg')
# Arna SSO integration
ARNA_SSO_BASE_URL = os.getenv('ARNA_SSO_BASE_URL', 'https://sso.arnatech.id/api')
SSO_IAM_PROVISION_ON_REGISTER = os.getenv(
    'SSO_IAM_PROVISION_ON_REGISTER', 'True'
).lower() in ('true', '1', 'yes')

# AI Copilot (LLM)
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')
DEEPSEEK_VISION_MODEL = os.getenv('DEEPSEEK_VISION_MODEL', 'deepseek-chat')

# django-q2 async jobs
Q_CLUSTER = {
    'name': 'arna_site',
    'workers': int(os.getenv('Q_CLUSTER_WORKERS', '2')),
    'timeout': int(os.getenv('Q_CLUSTER_TIMEOUT', '180')),
    'retry': int(os.getenv('Q_CLUSTER_RETRY', '240')),
    'queue_limit': int(os.getenv('Q_CLUSTER_QUEUE_LIMIT', '500')),
    'bulk': int(os.getenv('Q_CLUSTER_BULK', '10')),
    'orm': 'default',
    'redis': os.getenv('REDIS_URL', 'redis://localhost:6379/1'),
}

# JWT verification — public key issued by Arna SSO (RS256)
_jwt_key_raw = os.getenv('SSO_JWT_PUBLIC_KEY_PATH', 'public.pem')
SSO_JWT_PUBLIC_KEY_PATH = str(
    BASE_DIR / _jwt_key_raw if not os.path.isabs(_jwt_key_raw) else Path(_jwt_key_raw)
)
SSO_JWT_ALGORITHM = 'RS256'
SSO_JWT_AUDIENCE = os.getenv('SSO_JWT_AUDIENCE', '')

# CORS
CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
CORS_ALLOW_ALL_ORIGINS = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')
CORS_ALLOW_CREDENTIALS = os.getenv('CORS_ALLOW_CREDENTIALS', 'False').lower() in ('true', '1', 'yes')

# Swagger / drf-yasg
SWAGGER_SETTINGS = {
    'USE_SESSION_AUTH': False,
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': 'JWT token dari Arna SSO. Format: **Bearer &lt;token&gt;**',
        }
    },
    'DEFAULT_INFO': None,
    'PERSIST_AUTH': True,
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
