import uuid
from django.apps import AppConfig
from django.db.models.signals import post_migrate


def auto_seed_public_tenant(sender, **kwargs):
    """
    Automatically creates the 'public' tenant and maps it to 'localhost'
    whenever migrations run on the public schema. 
    This prevents the 'No tenant for hostname' 404 error on fresh installs.
    """
    # django-tenants passes `schema_name` to post_migrate signals
    schema_name = kwargs.get('schema_name', 'public')
    if schema_name != 'public':
        return

    from core.models import Tenant, Domain, Template, TemplateSection, TemplateBlock
    
    public_tenant, created = Tenant.objects.get_or_create(
        schema_name='public',
        defaults={
            'name': 'ArnaSite Global',
            'slug': 'public',
            'sso_organization_id': uuid.uuid4()
        }
    )
    
    import os
    domain_name = os.getenv('PUBLIC_DOMAIN_NAME', 'localhost')
    
    if created:
        Domain.objects.get_or_create(
            domain=domain_name,
            defaults={'tenant': public_tenant, 'is_primary': True}
        )

        template, _ = Template.objects.get_or_create(name='Modern Business', slug='modern-business')
        section, _ = TemplateSection.objects.get_or_create(template=template, type='hero', order=1)
        TemplateBlock.objects.get_or_create(section=section, title='Welcome to our Business', order=1)


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        post_migrate.connect(auto_seed_public_tenant, sender=self)
