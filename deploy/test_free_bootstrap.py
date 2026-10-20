"""Pure HTTP-contract and health checks with synthetic settings, no production DB."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(DJANGO_SETTINGS_MODULE='config.release_test_settings', SECRET_KEY='synthetic-release-check',
                 DEBUG='false', DB_HOST='unreachable-synthetic', DB_PASSWORD='synthetic-only')
import django
django.setup()
from django.core.management import call_command
call_command('check')
call_command('test', 'core.test_commerce_bootstrap', 'core.test_release_health', verbosity=2)
