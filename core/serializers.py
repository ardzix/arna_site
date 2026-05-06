from rest_framework import serializers
from core.models import (
    Template, TemplatePage, TemplateSection, TemplateBlock, TemplateListItem,
    Tenant, Domain,
)


# ─── Domain / Tenant ──────────────────────────────────────────────────────────

class DomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = Domain
        fields = ['id', 'domain', 'is_primary']
        read_only_fields = ['id', 'is_primary']

    def validate_domain(self, value):
        instance = self.instance
        qs = Domain.objects.filter(domain=value)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Domain ini sudah terdaftar.")
        return value


class TenantSerializer(serializers.ModelSerializer):
    domains = DomainSerializer(many=True, read_only=True)

    class Meta:
        model = Tenant
        fields = ['id', 'name', 'slug', 'schema_name', 'sso_organization_id',
                  'plan', 'tenancy_mode', 'shared_pool_key',
                  'is_active', 'created_on', 'domains']
        read_only_fields = ['id', 'slug', 'schema_name', 'sso_organization_id',
                            'plan', 'tenancy_mode', 'shared_pool_key',
                            'is_active', 'created_on', 'domains']


class TenantUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ['name']


# ─── Template Catalog ─────────────────────────────────────────────────────────

class TemplateListItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateListItem
        exclude = ('block',)


class TemplateBlockSerializer(serializers.ModelSerializer):
    items = TemplateListItemSerializer(many=True, read_only=True,
                                       source='list_items')

    class Meta:
        model = TemplateBlock
        exclude = ('section',)


class TemplateSectionSerializer(serializers.ModelSerializer):
    blocks = TemplateBlockSerializer(many=True, read_only=True)

    class Meta:
        model = TemplateSection
        fields = ['id', 'type', 'order', 'is_active', 'blocks']


class TemplatePageSerializer(serializers.ModelSerializer):
    sections = TemplateSectionSerializer(many=True, read_only=True)

    class Meta:
        model = TemplatePage
        fields = ['id', 'title', 'slug', 'order', 'is_home', 'sections']


class TemplateSerializer(serializers.ModelSerializer):
    """Full read-only serializer — katalog publik dan tenant browse."""
    pages = TemplatePageSerializer(many=True, read_only=True)

    class Meta:
        model = Template
        fields = ['id', 'name', 'slug', 'description', 'preview_image_url',
                  'category', 'is_active', 'is_published', 'source_tenant_schema',
                  'pages']


class TemplateWriteSerializer(serializers.ModelSerializer):
    """
    Untuk tenant membuat / mengubah template miliknya sendiri.
    `source_tenant_schema` diisi otomatis dari request, tidak dari user input.
    """
    class Meta:
        model = Template
        fields = ['name', 'slug', 'description', 'preview_image_url', 'category']

    def validate_slug(self, value):
        instance = self.instance
        qs = Template.objects.filter(slug=value)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Slug template ini sudah digunakan.")
        return value


# ─── Tenant Registration ──────────────────────────────────────────────────────

class TenantRegistrationSerializer(serializers.Serializer):
    name   = serializers.CharField(max_length=255,
                 help_text="Display name of the organization.")
    slug   = serializers.SlugField(max_length=100,
                 help_text="URL-friendly identifier, e.g. 'toko-budi'.")
    domain = serializers.CharField(max_length=253,
                 help_text="Primary domain, e.g. 'toko-budi.arnasite.id'.")
    plan   = serializers.ChoiceField(
        choices=[Tenant.PLAN_FREE, Tenant.PLAN_PRO, Tenant.PLAN_ENTERPRISE],
        required=False,
        default=Tenant.PLAN_FREE,
        help_text=(
            "Requested package plan. "
            "Default `free`. "
            "`free` and `pro` will be provisioned on shared schema pool. "
            "`enterprise` requires special privilege and gets dedicated schema."
        ),
    )

    def validate_slug(self, value):
        if Tenant.objects.filter(slug=value).exists():
            raise serializers.ValidationError("Slug ini sudah digunakan.")
        schema_name = value.replace("-", "_")
        if Tenant.objects.filter(schema_name=schema_name).exists():
            raise serializers.ValidationError("Schema yang dihasilkan dari slug ini sudah ada.")
        return value

    def validate_domain(self, value):
        if Domain.objects.filter(domain=value).exists():
            raise serializers.ValidationError("Domain ini sudah terdaftar.")
        return value


class PremiumCheckoutSerializer(serializers.Serializer):
    payer_email = serializers.EmailField(required=False, allow_blank=False)
    description = serializers.CharField(required=False, allow_blank=True, max_length=255)
    success_redirect_url = serializers.URLField(required=False)
    failure_redirect_url = serializers.URLField(required=False)
    customer = serializers.JSONField(required=False)
