from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from core.models import Class, Student, StudentClassEnrollment, ClassRosterEntry


User = get_user_model()


class Command(BaseCommand):
    help = 'İlkin demo məlumatları yaradır: inzibatçı, müəllim, siniflər və şagirdlər.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--noinput',
            action='store_true',
            dest='noinput',
            help='Təsdiqləmə sorğusunu keçin',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('İlkin məlumatlar yaradılır...')

        admin, admin_created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'first_name': 'Sistem',
                'last_name': 'İnzibatçısı',
                'staff': 0,
                'subject': 'İnzibatçılıq',
                'is_superuser': True,
                'is_staff': True,
                'is_active': True,
            }
        )
        if admin_created:
            admin.set_password('admin12345')
            admin.save()
            self.stdout.write(self.style.SUCCESS(f'✓ İnzibatçı yaradıldı: admin / admin12345'))
        else:
            self.stdout.write(self.style.WARNING('⚠ İnzibatçı artıq mövcuddur: admin'))

        teacher1, t1_created = User.objects.get_or_create(
            username='teacher1',
            defaults={
                'email': 'muellim1@example.com',
                'first_name': 'Əli',
                'last_name': 'Məmmədov',
                'staff': 1,
                'subject': 'Riyaziyyat',
                'is_staff': True,
                'is_active': True,
            }
        )
        if t1_created:
            teacher1.set_password('teacher12345')
            teacher1.save()
            self.stdout.write(self.style.SUCCESS(f'✓ Müəllim yaradıldı: teacher1 / teacher12345 (Riyaziyyat)'))

        teacher2, t2_created = User.objects.get_or_create(
            username='teacher2',
            defaults={
                'email': 'muellim2@example.com',
                'first_name': 'Aygün',
                'last_name': 'Hüseynova',
                'staff': 1,
                'subject': 'Fizika',
                'is_staff': True,
                'is_active': True,
            }
        )
        if t2_created:
            teacher2.set_password('teacher12345')
            teacher2.save()
            self.stdout.write(self.style.SUCCESS(f'✓ Müəllim yaradıldı: teacher2 / teacher12345 (Fizika)'))

        class1, c1_created = Class.objects.get_or_create(
            name='10-cu sinif Riyaziyyat - A',
            defaults={'teacher': teacher1}
        )
        if c1_created:
            self.stdout.write(self.style.SUCCESS(f'✓ Sinif yaradıldı: {class1.name}'))

        class2, c2_created = Class.objects.get_or_create(
            name='11-ci sinif Fizika - B',
            defaults={'teacher': teacher2}
        )
        if c2_created:
            self.stdout.write(self.style.SUCCESS(f'✓ Sinif yaradıldı: {class2.name}'))

        class3, c3_created = Class.objects.get_or_create(
            name='9-cu sinif Riyaziyyat - Əlavə',
            defaults={'teacher': teacher1}
        )
        if c3_created:
            self.stdout.write(self.style.SUCCESS(f'✓ Sinif yaradıldı: {class3.name}'))

        demo_students = [
            ('Emil', 'Quliyev', class1, 'i/e', 9),
            ('Məhəmməd', 'Əliyev', class1, 'q/b', 7),
            ('Leyla', 'Məmmədova', class1, 'ü/q', 10),
            ('Dəniz', 'Tağıyev', class1, 'i/e', 8),
            ('Səbinə', 'Kazımova', class1, 'q/b', 6),
            ('Cəmil', 'Mərtanov', class2, 'q/b', 5),
            ('Nigar', 'Şəkərova', class2, 'i/e', 10),
            ('Farid', 'Qasımov', class2, 'ü/q', 8),
            ('Aysel', 'İbrahimova', class2, 'i/e', 9),
            ('Namiq', 'Rzayev', class3, 'i/e', 8),
            ('Lalə', 'Mustafayeva', class3, 'q/b', 7),
            ('Elçin', 'Əhmədov', class3, 'ü/q', 9),
        ]

        for fname, lname, cls_obj, att_status, grade in demo_students:
            student, s_created = Student.objects.get_or_create(
                firstname=fname,
                lastname=lname,
                defaults={
                    'attendance_grades': grade,
                    'activity_status': True,
                }
            )
            StudentClassEnrollment.objects.get_or_create(
                student=student,
                class_assigned=cls_obj,
                defaults={
                    'attendance_status': att_status,
                    'evaluation_grade': grade,
                }
            )
            ClassRosterEntry.objects.get_or_create(
                full_name=f'{fname} {lname}',
                current_class=cls_obj,
                defaults={
                    'participants': att_status,
                }
            )
            if s_created:
                self.stdout.write(f'  • {fname} {lname} (İstifadəçi: {student.username}, Şifrə: {student.password}) - {cls_obj.name} sinifinə yazıldı')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═══════════════════════════════════════════'))
        self.stdout.write(self.style.SUCCESS(' Məlumatlar uğurla yaradıldı!'))
        self.stdout.write(self.style.SUCCESS('═══════════════════════════════════════════'))
        self.stdout.write('')
        self.stdout.write('Giriş Məlumatları:')
        self.stdout.write(self.style.SUCCESS('  İnzibatçı:  admin       / admin12345'))
        self.stdout.write(self.style.SUCCESS('  Müəllim 1:  teacher1    / teacher12345 (Riyaziyyat)'))
        self.stdout.write(self.style.SUCCESS('  Müəllim 2:  teacher2    / teacher12345 (Fizika)'))
        self.stdout.write('')
