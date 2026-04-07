from rest_framework import serializers
from core.models import Template, TemplateSection, TemplateBlock, TemplateListItem

class TemplateListItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateListItem
        exclude = ('block',)

class TemplateBlockSerializer(serializers.ModelSerializer):
    items = TemplateListItemSerializer(many=True, read_only=True)

    class Meta:
        model = TemplateBlock
        exclude = ('section',)

class TemplateSectionSerializer(serializers.ModelSerializer):
    blocks = TemplateBlockSerializer(many=True, read_only=True)

    class Meta:
        model = TemplateSection
        exclude = ('template',)

class TemplateSerializer(serializers.ModelSerializer):
    sections = TemplateSectionSerializer(many=True, read_only=True)

    class Meta:
        model = Template
        fields = '__all__'
