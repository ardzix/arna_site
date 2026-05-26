from django.db import transaction
from rest_framework import serializers
from core.models import (
    Template, TemplatePage, TemplateSection, TemplateBlock, TemplateListItem,
    Tenant, Domain,
)


# ─── Domain / Tenant ──────────────────────────────────────────────────────────

class DomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = Domain
        fields = [
            'id', 'domain', 'is_primary', 'is_primary_frontend',
            'role', 'status', 'target_backend_domain',
            'verification_method', 'verification_token', 'verified_at',
        ]
        read_only_fields = [
            'id', 'is_primary', 'target_backend_domain',
            'verification_method', 'verification_token', 'verified_at',
        ]

    def validate_domain(self, value):
        instance = self.instance
        qs = Domain.objects.filter(domain=value)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Domain ini sudah terdaftar.")
        return value

    def validate_role(self, value):
        allowed = {
            Domain.ROLE_FRONTEND_CUSTOM,
            Domain.ROLE_FRONTEND_DEFAULT,
            Domain.ROLE_BACKEND_PRIMARY,
        }
        if value not in allowed:
            raise serializers.ValidationError("Role domain tidak valid.")
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


class TemplateListItemWriteSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    icon = serializers.CharField(required=False, allow_blank=True, default="")
    order = serializers.IntegerField(min_value=0, required=False, default=0)


class TemplateBlockWriteSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True, default="")
    subtitle = serializers.CharField(required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    extra = serializers.JSONField(required=False, default=dict)
    order = serializers.IntegerField(min_value=0)
    items = TemplateListItemWriteSerializer(many=True, required=False, default=list)


class TemplateSectionWriteSerializer(serializers.Serializer):
    type = serializers.CharField()
    order = serializers.IntegerField(min_value=0)
    is_active = serializers.BooleanField(required=False, default=True)
    blocks = TemplateBlockWriteSerializer(many=True, required=False, default=list)


class TemplatePageWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=255)
    order = serializers.IntegerField(min_value=0, required=False, default=0)
    is_home = serializers.BooleanField(required=False, default=False)
    sections = TemplateSectionWriteSerializer(many=True, required=False, default=list)


class TemplateManualCreateSerializer(serializers.ModelSerializer):
    """
    Create template with full nested structure:
    template -> pages -> sections -> blocks -> items.
    """
    pages = TemplatePageWriteSerializer(many=True)

    class Meta:
        model = Template
        fields = ['name', 'slug', 'description', 'preview_image_url', 'category', 'pages']

    def validate_pages(self, value):
        if not value:
            raise serializers.ValidationError("At least one page is required.")
        home_count = sum(1 for p in value if p.get("is_home"))
        if home_count != 1:
            raise serializers.ValidationError("Exactly one page must be marked as is_home=true.")
        return value

    def validate_slug(self, value):
        qs = Template.objects.filter(slug=value)
        if qs.exists():
            raise serializers.ValidationError("Slug template ini sudah digunakan.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        pages_data = validated_data.pop("pages", [])
        template = Template.objects.create(**validated_data)

        for page_data in pages_data:
            sections_data = page_data.pop("sections", [])
            page = TemplatePage.objects.create(template=template, **page_data)
            for section_data in sections_data:
                blocks_data = section_data.pop("blocks", [])
                section = TemplateSection.objects.create(
                    template=template,
                    page=page,
                    **section_data,
                )
                for block_data in blocks_data:
                    items_data = block_data.pop("items", [])
                    block = TemplateBlock.objects.create(section=section, **block_data)
                    for item_data in items_data:
                        TemplateListItem.objects.create(block=block, **item_data)

        return template


# ─── Tenant Registration ──────────────────────────────────────────────────────

class TenantRegistrationSerializer(serializers.Serializer):
    name   = serializers.CharField(max_length=255,
                 help_text="Display name of the organization.")
    slug   = serializers.SlugField(max_length=100,
                 help_text="URL-friendly identifier, e.g. 'toko-budi'.")
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


class PremiumCheckoutSerializer(serializers.Serializer):
    payer_email = serializers.EmailField(required=False, allow_blank=False)
    description = serializers.CharField(required=False, allow_blank=True, max_length=255)
    success_redirect_url = serializers.URLField(required=False)
    failure_redirect_url = serializers.URLField(required=False)
    customer = serializers.JSONField(required=False)
