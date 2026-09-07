from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_add_lesson_link_and_is_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='lesson',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Dərsin Başlama Vaxtı'),
        ),
    ]
