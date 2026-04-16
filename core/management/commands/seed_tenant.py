import uuid
from django.core.management.base import BaseCommand
from core.models import Tenant, Domain, Template, TemplateSection, TemplateBlock


class Command(BaseCommand):
    help = 'Seeds the database with the initial public schema, templates, and a test tenant.'

    def handle(self, *args, **options):
        self.stdout.write("Starting database seed...")

        # 1. Create or get the Public Tenant
        public_tenant, created = Tenant.objects.get_or_create(
            schema_name='public',
            defaults={
                'name': 'ArnaSite Global',
                'slug': 'public',
                'sso_organization_id': uuid.uuid4()
            }
        )

        # Selalu pastikan localhost terdaftar (idempotent)
        _, dom_created = Domain.objects.get_or_create(
            domain='localhost',
            defaults={'tenant': public_tenant, 'is_primary': not Domain.objects.filter(tenant=public_tenant).exists()}
        )
        if dom_created:
            self.stdout.write(self.style.SUCCESS("Registered localhost -> public schema."))

        if created:
            self.stdout.write(self.style.SUCCESS("Created Public Tenant."))
        else:
            self.stdout.write(self.style.WARNING("Public tenant already exists."))

        template, template_created = Template.objects.get_or_create(
            name='Modern Business',
            slug='modern-business',
        )
        section, _ = TemplateSection.objects.get_or_create(
            template=template,
            type='hero',
            order=1,
        )
        TemplateBlock.objects.get_or_create(
            section=section,
            title='Welcome to our Business',
            order=1,
        )
        if template_created:
            self.stdout.write(self.style.SUCCESS("Created Dummy Master Template."))
        else:
            self.stdout.write(self.style.WARNING("Dummy Master Template already exists."))

        # 2. Create or get the Test Tenant
        test_tenant, created = Tenant.objects.get_or_create(
            schema_name='tenant_test_01',
            defaults={
                'name': 'Toko Testing',
                'slug': 'toko-testing',
                'sso_organization_id': uuid.uuid4()
            }
        )

        if created:
            Domain.objects.get_or_create(
                domain='test.localhost',
                defaults={'tenant': test_tenant, 'is_primary': True}
            )
            self.stdout.write(self.style.SUCCESS("Created Test Tenant (tenant_test_01)."))
        else:
            self.stdout.write(self.style.WARNING("Test tenant already exists. Skipping."))

        self.stdout.write(self.style.SUCCESS("\nSeeding complete!"))
        self.stdout.write(self.style.NOTICE(
            "Next step: Run `python manage.py migrate_schemas` to generate the tables for tenant_test_01."
        ))
