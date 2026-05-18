from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sites', '0002_page_section_page'),
    ]

    operations = [
        migrations.AddField(
            model_name='page',
            name='source_template_id',
            field=models.UUIDField(
                blank=True,
                help_text='Root template UUID used to generate this page.',
                null=True,
            ),
        ),
    ]

