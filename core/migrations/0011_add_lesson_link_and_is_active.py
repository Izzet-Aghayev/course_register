from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_feedback'),
    ]

    operations = [
        migrations.AddField(
            model_name='lesson',
            name='is_active',
            field=models.BooleanField(default=False, verbose_name='Canlı Dərs Aktivdir'),
        ),
        migrations.AddField(
            model_name='lesson',
            name='lesson_link',
            field=models.URLField(blank=True, null=True, verbose_name='Dərs Linki'),
        ),
    ]
