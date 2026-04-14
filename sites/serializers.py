from rest_framework import serializers
from sites.models import Page, Section, ContentBlock, ListItem


class ListItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListItem
        fields = ["id", "block", "title", "description", "icon", "order",
                  "template_list_item_id"]
        read_only_fields = ["id", "template_list_item_id"]


class ContentBlockSerializer(serializers.ModelSerializer):
    items = ListItemSerializer(many=True, read_only=True)

    class Meta:
        model = ContentBlock
        fields = ["id", "section", "title", "subtitle", "description",
                  "image_url", "extra", "order", "template_block_id", "items"]
        read_only_fields = ["id", "template_block_id"]


class SectionSerializer(serializers.ModelSerializer):
    blocks = ContentBlockSerializer(many=True, read_only=True)

    class Meta:
        model = Section
        fields = ["id", "page", "type", "order", "is_active",
                  "template_section_id", "blocks"]
        read_only_fields = ["id", "template_section_id"]


class PageSerializer(serializers.ModelSerializer):
    """Serializer ringkas untuk list/create/update page."""
    class Meta:
        model = Page
        fields = ["id", "title", "slug", "is_home", "is_active", "order",
                  "meta_title", "meta_description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class PageDetailSerializer(serializers.ModelSerializer):
    """Serializer lengkap untuk detail page — sections + blocks + items di-embed."""
    sections = SectionSerializer(many=True, read_only=True)

    class Meta:
        model = Page
        fields = ["id", "title", "slug", "is_home", "is_active", "order",
                  "meta_title", "meta_description", "created_at", "updated_at",
                  "sections"]
        read_only_fields = ["id", "created_at", "updated_at"]
