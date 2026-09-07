from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def replace_null_reklam_identity_fields(apps, schema_editor):
    """Preserve existing adverts before their identity fields become required."""
    Reklam = apps.get_model('core', 'Reklam')
    Reklam.objects.filter(ad__isnull=True).update(ad='')
    Reklam.objects.filter(soyad__isnull=True).update(soyad='')
    Reklam.objects.filter(ixtisas_fenni__isnull=True).update(ixtisas_fenni='')


def preserve_legacy_attendance_roster_links(apps, schema_editor):
    """Move pre-upgrade roster IDs out of Attendance.student before retargeting it."""
    from django.db.models import F

    Attendance = apps.get_model('core', 'Attendance')
    Attendance.objects.filter(student_id__isnull=False).update(
        roster_entry_id=F('student_id'),
        student_id=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_add_started_at_to_lesson'),
    ]

    operations = [
        migrations.RunPython(replace_null_reklam_identity_fields, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name='attendance',
            options={
                'ordering': ['lesson__date'],
                'verbose_name': 'Davamiyyət / Qiymət',
                'verbose_name_plural': 'Davamiyyət / Qiymətlər',
            },
        ),
        migrations.AlterUniqueTogether(
            name='attendance',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='attendance',
            name='modified_at',
            field=models.DateTimeField(auto_now=True, verbose_name='Son Dəyişdirilmə Tarixi'),
        ),
        migrations.AddField(
            model_name='attendance',
            name='roster_entry',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='attendance_records',
                to='core.classrosterentry',
                verbose_name='Şagird (Köhnə Qeydiyyat)',
            ),
        ),
        migrations.RunPython(preserve_legacy_attendance_roster_links, migrations.RunPython.noop),
        migrations.AddField(
            model_name='attendance',
            name='updated_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='attendance_changes',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Son Dəyişdirən',
            ),
        ),
        migrations.AlterField(
            model_name='attendance',
            name='student',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='attendance_records',
                to='core.student',
                verbose_name='Şagird',
            ),
        ),
        migrations.AlterField(
            model_name='class',
            name='name',
            field=models.CharField(max_length=150, verbose_name='Sinif adı'),
        ),
        migrations.AlterUniqueTogether(
            name='class',
            unique_together={('name', 'teacher')},
        ),
        migrations.AlterField(
            model_name='reklam',
            name='ad',
            field=models.CharField(max_length=100, verbose_name='Ad'),
        ),
        migrations.AlterField(
            model_name='reklam',
            name='soyad',
            field=models.CharField(max_length=100, verbose_name='Soyad'),
        ),
        migrations.AlterField(
            model_name='reklam',
            name='ixtisas_fenni',
            field=models.CharField(max_length=250, verbose_name='İxtisas / Fənn'),
        ),
    ]
