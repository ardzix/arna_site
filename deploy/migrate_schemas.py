"""One-off public and distinct tenant-schema migration gate; never seed demo data."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.core.management import call_command
from django_tenants.utils import get_tenant_model

call_command('migrate_schemas', schema_name='public', interactive=False, verbosity=1)
schemas = sorted(set(get_tenant_model().objects.values_list('schema_name', flat=True)) - {'public'})
for schema in schemas:
    call_command('migrate_schemas', schema_name=schema, interactive=False, verbosity=1)
print('Public and all registered distinct tenant schemas migrated successfully')
