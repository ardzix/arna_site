from rest_framework import serializers
from sites.models import Section, ContentBlock, ListItem

class ListItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListItem
        fields = ["id", "block", "title", "description", "icon", "order", "template_list_item_id"]
        read_only_fields = ["id", "template_list_item_id"]

class ContentBlockSerializer(serializers.ModelSerializer):
    items = ListItemSerializer(many=True, read_only=True)

    class Meta:
        model = ContentBlock
        fields = [
            "id", "section", "title", "subtitle", "description", 
            "image_url", "extra", "order", "template_block_id", "items"
        ]
        read_only_fields = ["id", "template_block_id"]

class SectionSerializer(serializers.ModelSerializer):
    blocks = ContentBlockSerializer(many=True, read_only=True)

    class Meta:
        model = Section
        fields = ["id", "type", "order", "is_active", "template_section_id", "blocks"]
        read_only_fields = ["id", "template_section_id"]
