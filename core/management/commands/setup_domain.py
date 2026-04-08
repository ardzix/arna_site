import uuid
from django.core.management.base import BaseCommand
from core.models import Tenant, Domain

import os
import sys

class Command(BaseCommand):
    help = 'Registers a production domain for the public schema.'

    def handle(self, *args, **options):
        domain_name = os.getenv('PUBLIC_DOMAIN_NAME')
        if not domain_name:
            self.stdout.write(self.style.ERROR("❌ ENVIRONMENT VARIABLE 'PUBLIC_DOMAIN_NAME' IS MISSING!"))
            sys.exit(1)

        # Pastikan public tenant eksis
        public_tenant, created = Tenant.objects.get_or_create(
            schema_name='public',
            defaults={
                'name': 'Arna Site Public',
                'slug': 'public',
                'sso_organization_id': uuid.uuid4()
            }
        )
        
        # Daftarkan domain untuk public tenant tersebut
        domain, dom_created = Domain.objects.get_or_create(
            domain=domain_name,
            defaults={'tenant': public_tenant, 'is_primary': True}
        )
        
        if dom_created:
            self.stdout.write(self.style.SUCCESS(f"✅ Successfully registered production domain '{domain_name}' to public schema!"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️ Domain '{domain_name}' is already registered to public schema."))
