from .settings import *

CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
ALLOWED_HOSTS = ['testserver', 'localhost']
