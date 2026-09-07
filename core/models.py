import random
import string
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from dateutil.relativedelta import relativedelta


def capitalize_az(text):
    if not text:
        return text
    text = str(text).strip()
    if not text:
        return text

    def _cap_token(t):
        if not t:
            return t
        subparts = t.split('-')
        return '-'.join(p[0].upper() + p[1:] if p else '' for p in subparts)

    return ' '.join(_cap_token(part) for part in text.split(' ') if part)


class User(AbstractUser):
    ROLE_DIGER = 0
    ROLE_MUALLIM = 1
    ROLE_KURS_INZIBATCHISI = 2

    STAFF_CHOICES = (
        (ROLE_MUALLIM, 'Müəllim'),
        (ROLE_KURS_INZIBATCHISI, 'Kurs-inzibatçısı'),
        (ROLE_DIGER, 'Digər'),
    )

    REKLAM_ICAZESI_CHOICES = (
        ('default', 'Varsayılan / Limitsiz'),
        ('limitsiz', 'Limitsiz'),
        ('qadagan', 'Qadağan edilib'),
    )

    username = models.CharField(
        max_length=150,
        unique=True,
        verbose_name='İstifadəçi adı'
    )
    staff = models.IntegerField(choices=STAFF_CHOICES, default=0, verbose_name='Vəzifə')
    subject = models.CharField(max_length=60, verbose_name='Fənn', blank=True, default='')
    reklam_icazesi = models.CharField(
        max_length=20,
        choices=REKLAM_ICAZESI_CHOICES,
        default='default',
        verbose_name='Reklam icazəsi'
    )
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_users',
        verbose_name='Yaradan'
    )
    teacher_creation_limit = models.IntegerField(
        default=0,
        verbose_name='Müəllim yaratma limiti'
    )
    lesson_link = models.URLField(
        blank=True,
        null=True,
        verbose_name='Xüsusi Dərs Linki'
    )
    activation_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Aktivləşmə tarixi'
    )
    deactivation_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Deaktivləşmə tarixi'
    )

    REQUIRED_FIELDS = ['staff', 'email']

    class Meta:
        verbose_name = 'İstifadəçi'
        verbose_name_plural = 'İstifadəçilər'
        ordering = ['-is_superuser', '-staff', 'username']

    def __str__(self):
        role_label = self.get_role_display()
        return f'{self.get_full_name() or self.username} ({role_label})'

    def get_role_display(self):
        if self.is_superuser:
            return 'İnzibatçı'
        return dict(self.STAFF_CHOICES).get(self.staff, 'Digər')

    def save(self, *args, **kwargs):
        if self.first_name:
            self.first_name = capitalize_az(self.first_name)
        if self.last_name:
            self.last_name = capitalize_az(self.last_name)

        is_new = self.pk is None

        if is_new and not self.is_superuser:
            now = timezone.now()
            if self.activation_date is None:
                if self.staff in (self.ROLE_MUALLIM, self.ROLE_KURS_INZIBATCHISI):
                    self.activation_date = now
            if self.deactivation_date is None:
                if self.staff in (self.ROLE_MUALLIM, self.ROLE_KURS_INZIBATCHISI):
                    self.deactivation_date = now + relativedelta(months=1)

        if is_new:
            if self.is_superuser:
                self.teacher_creation_limit = 1000
            elif self.staff == self.ROLE_KURS_INZIBATCHISI:
                self.teacher_creation_limit = 10
            elif self.staff == self.ROLE_MUALLIM:
                self.teacher_creation_limit = 0

        super().save(*args, **kwargs)

    @property
    def is_teacher(self):
        return self.staff == self.ROLE_MUALLIM or self.is_superuser

    @property
    def is_course_admin(self):
        return self.staff == self.ROLE_KURS_INZIBATCHISI

    @property
    def is_course_admin_or_higher(self):
        return self.is_superuser or self.is_course_admin

    @property
    def can_access_django_admin(self):
        return self.is_superuser

    @property
    def can_post_reklam(self):
        return self.reklam_icazesi != 'qadagan'

    def get_active_reklam_count(self):
        return self.reklamlar.count()

    def is_account_expired(self):
        if self.is_superuser:
            return False
        if self.deactivation_date is None:
            return False
        return timezone.now() > self.deactivation_date


class Class(models.Model):
    name = models.CharField(max_length=150, verbose_name='Sinif adı')
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='classes_taught',
        verbose_name='Müəllim'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_classes',
        verbose_name='Yaradan'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaradılma tarixi')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Yenilənmə tarixi')

    class Meta:
        verbose_name = 'Sinif'
        verbose_name_plural = 'Siniflər'
        ordering = ['name']
        unique_together = [('name', 'teacher')]

    def __str__(self):
        return self.name

    @property
    def student_count(self):
        return self.students.count()

    @property
    def roster_entry_count(self):
        return self.roster_entries.count()


class ClassRosterEntry(models.Model):
    ATTENDANCE_CHOICES = (
        ('', '--------'),
        ('i/e', 'İştirak edir'),
        ('q/b', 'Qayıb'),
        ('ü/q', 'Üzrlü Qayıb'),
    )

    full_name = models.CharField(max_length=150, verbose_name='Tam adı')
    current_class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='roster_entries',
        verbose_name='Cari sinif'
    )
    participants = models.CharField(
        max_length=10,
        choices=ATTENDANCE_CHOICES,
        default='',
        blank=True,
        verbose_name='Davamiyyət'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_roster_entries',
        verbose_name='Yaradan'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaradılma tarixi')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Yenilənmə tarixi')

    class Meta:
        verbose_name = 'Sinif Qeydiyyatı'
        verbose_name_plural = 'Sinif Qeydiyyətləri'
        ordering = ['full_name']

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        if self.full_name:
            self.full_name = capitalize_az(self.full_name)
        super().save(*args, **kwargs)

    @property
    def participant_label(self):
        return dict(self.ATTENDANCE_CHOICES).get(self.participants, '--------')


AZ_TRANSLIT = {
    'Ç': 'C', 'ç': 'c',
    'Ə': 'E', 'ə': 'e',
    'Ğ': 'G', 'ğ': 'g',
    'I': 'I', 'ı': 'i',
    'İ': 'I', 'i': 'i',
    'Ö': 'O', 'ö': 'o',
    'Ş': 'S', 'ş': 's',
    'Ü': 'U', 'ü': 'u',
}


def azerbaijani_transliterate(text):
    result = []
    for char in text:
        if char in AZ_TRANSLIT:
            result.append(AZ_TRANSLIT[char])
        else:
            result.append(char)
    return ''.join(result).lower()


def generate_student_username(firstname, lastname):
    firstname = str(firstname or '').strip()
    lastname = str(lastname or '').strip()
    if not firstname or not lastname:
        first_letter = 's'
        last_clean = 'shagird'
    else:
        first_token = firstname.split()[0]
        last_token = lastname.split()[0]
        first_ascii = azerbaijani_transliterate(first_token)
        last_ascii = azerbaijani_transliterate(last_token)
        first_letter = first_ascii[0] if first_ascii else 's'
        last_clean = ''.join(
            ch for ch in last_ascii if ch.isascii() and ch.isalpha()
        ) or 'shagird'
    suffix = ''.join(random.choices(string.digits, k=3))
    return f'{first_letter}{last_clean}c{suffix}'


def generate_student_password():
    digits = ''.join(random.choices(string.digits, k=6))
    letter = random.choice(string.ascii_lowercase)
    return f'{digits}{letter}'


class Student(models.Model):
    ACTIVITY_CHOICES = (
        (True, 'Aktiv'),
        (False, 'Deaktiv'),
    )

    firstname = models.CharField(max_length=100, verbose_name='Ad')
    lastname = models.CharField(max_length=100, verbose_name='Soyad')
    username = models.CharField(max_length=150, unique=True, blank=True, verbose_name='İstifadəçi adı')
    password = models.CharField(max_length=150, blank=True, verbose_name='Şifrə')
    activity_status = models.BooleanField(choices=ACTIVITY_CHOICES, default=True, verbose_name='Aktivlik statusu')
    attendance_grades = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        default=0,
        verbose_name='Davamiyyət Qiyməti (0-10)'
    )
    classes = models.ManyToManyField(
        Class,
        through='StudentClassEnrollment',
        related_name='students',
        blank=True,
        verbose_name='Siniflər'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_students',
        verbose_name='Yaradan'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaradılma tarixi')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Yenilənmə tarixi')

    class Meta:
        verbose_name = 'Şagird'
        verbose_name_plural = 'Şagirdlər'
        ordering = ['lastname', 'firstname']

    def __str__(self):
        return f'{self.lastname} {self.firstname}'

    def save(self, *args, **kwargs):
        if self.firstname:
            self.firstname = capitalize_az(self.firstname)
        if self.lastname:
            self.lastname = capitalize_az(self.lastname)
        if not self.username:
            candidate = generate_student_username(self.firstname, self.lastname)
            attempts = 0
            while attempts < 50:
                exists = (
                    Student.objects.filter(username=candidate)
                    .exclude(pk=self.pk)
                    .exists()
                )
                if not exists:
                    break
                candidate = generate_student_username(self.firstname, self.lastname)
                attempts += 1
            self.username = candidate
        if not self.password:
            self.password = generate_student_password()
        super().save(*args, **kwargs)

    def get_full_name(self):
        return f'{self.firstname} {self.lastname}'

    @property
    def full_name(self):
        return f"{self.firstname} {self.lastname}".strip()


class Lesson(models.Model):
    class_assigned = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='lessons',
        verbose_name='Sinif'
    )
    title_topic = models.CharField(max_length=250, verbose_name='Mövzu')
    date = models.DateField(verbose_name='Tarix')
    start_time = models.TimeField(verbose_name='Başlama vaxtı')
    end_time = models.TimeField(verbose_name='Bitmə vaxtı')
    lesson_link = models.URLField(
        blank=True,
        null=True,
        verbose_name='Dərs Linki'
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name='Canlı Dərs Aktivdir'
    )
    started_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Dərsin Başlama Vaxtı'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_lessons',
        verbose_name='Yaradan'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaradılma tarixi')

    class Meta:
        verbose_name = 'Dərs'
        verbose_name_plural = 'Dərslər'
        ordering = ['-date', '-start_time']

    def __str__(self):
        return f'{self.class_assigned.name} - {self.title_topic} ({self.date})'

    def get_absolute_url(self):
        return reverse('core:lesson_detail', kwargs={'pk': self.pk})

    def clean(self):
        super().clean()
        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
                raise ValidationError({
                    'start_time': 'Başlama vaxtı bitmə vaxtından kiçik olmalıdır.',
                    'end_time': 'Bitmə vaxtı başlama vaxtından böyük olmalıdır.',
                })
        if self.class_assigned_id and self.date and self.start_time and self.end_time:
            teacher_id = self.class_assigned.teacher_id
            if teacher_id:
                Class.objects.select_for_update().filter(teacher_id=teacher_id).exists()
                overlapping = Lesson.objects.select_related('class_assigned').filter(
                    class_assigned__teacher_id=teacher_id,
                    date=self.date,
                ).exclude(pk=self.pk)
                for other in overlapping:
                    if (
                        other.start_time < self.end_time
                        and self.start_time < other.end_time
                    ):
                        raise ValidationError(
                            f'Bu vaxt intervalında müəllimin başqa dərsi var: '
                            f'{other.class_assigned.name} - {other.title_topic} '
                            f'({other.start_time} - {other.end_time}).'
                        )

    def save(self, *args, **kwargs):
        from django.db import transaction

        with transaction.atomic():
            self.full_clean()
            if self.pk is None and not self.lesson_link and self.class_assigned_id:
                try:
                    class_obj = Class.objects.select_related('teacher').get(pk=self.class_assigned_id)
                    if class_obj.teacher and class_obj.teacher.lesson_link:
                        self.lesson_link = class_obj.teacher.lesson_link
                except Class.DoesNotExist:
                    pass
            super().save(*args, **kwargs)

    @property
    def is_expired(self):
        try:
            now = timezone.now()
            lesson_end = timezone.make_aware(
                timezone.datetime.combine(self.date, self.end_time)
            )
            return now > lesson_end
        except Exception:
            return False

    @property
    def student_can_join_after_delay(self):
        if not self.is_active or not self.started_at or not self.lesson_link:
            return False
        if self.is_expired:
            return False
        try:
            from datetime import timedelta
            now = timezone.now()
            eligible_at = self.started_at + timedelta(seconds=30)
            return now >= eligible_at
        except Exception:
            return False

    @property
    def student_delay_seconds_remaining(self):
        if not self.is_active or not self.started_at:
            return 0
        if self.is_expired:
            return 0
        try:
            from datetime import timedelta
            now = timezone.now()
            eligible_at = self.started_at + timedelta(seconds=30)
            remaining = (eligible_at - now).total_seconds()
            return max(0, int(remaining))
        except Exception:
            return 0


class Attendance(models.Model):
    STATUS_CHOICES = (
        ('', '--------'),
        ('i/e', 'İştirak edir'),
        ('q/b', 'Qayıb'),
        ('gecikir', 'Gecikir'),
        ('icazəli', 'İcazəli'),
        ('ü/q', 'Üzrlü Qayıb'),
    )
    STATUS_GRADES = tuple((str(i), str(i)) for i in range(11))
    STATUS_ALL_CHOICES = STATUS_CHOICES + STATUS_GRADES

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='attendance_records',
        verbose_name='Dərs'
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='attendance_records',
        null=True,
        blank=True,
        verbose_name='Şagird'
    )
    roster_entry = models.ForeignKey(
        ClassRosterEntry,
        on_delete=models.SET_NULL,
        related_name='attendance_records',
        null=True,
        blank=True,
        verbose_name='Şagird (Köhnə Qeydiyyat)'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_ALL_CHOICES,
        default='',
        blank=True,
        verbose_name='Status'
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_changes',
        verbose_name='Son Dəyişdirən'
    )
    modified_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Son Dəyişdirilmə Tarixi'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaradılma tarixi')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Yenilənmə tarixi')

    class Meta:
        verbose_name = 'Davamiyyət / Qiymət'
        verbose_name_plural = 'Davamiyyət / Qiymətlər'
        ordering = ['lesson__date']
        constraints = [models.UniqueConstraint(fields=['lesson', 'student'], name='unique_attendance_lesson_student')]
        constraints = [models.UniqueConstraint(fields=['lesson', 'student'], name='unique_attendance_lesson_student')]

    def __str__(self):
        student_name = ''
        if self.student_id:
            student_name = self.student.get_full_name()
        elif self.roster_entry_id:
            student_name = self.roster_entry.full_name
        return f'{student_name} - {self.lesson.title_topic}: {self.status}'

    @property
    def status_label(self):
        return dict(self.STATUS_ALL_CHOICES).get(self.status, '--------')

    @property
    def student_display_name(self):
        if self.student_id:
            return self.student.get_full_name()
        if self.roster_entry_id:
            return self.roster_entry.full_name
        return ''


class StudentClassEnrollment(models.Model):
    ATTENDANCE_CHOICES = (
        ('', '--------'),
        ('i/e', 'İştirak edir'),
        ('q/b', 'Qayıb'),
        ('gecikir', 'Gecikir'),
        ('icazəli', 'İcazəli'),
        ('ü/q', 'Üzrlü Qayıb'),
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='enrollments',
        verbose_name='Şagird'
    )
    class_assigned = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='enrollments',
        verbose_name='Sinif'
    )
    attendance_status = models.CharField(
        max_length=20,
        choices=ATTENDANCE_CHOICES,
        default='i/e',
        verbose_name='Davamiyyət Statusu'
    )
    evaluation_grade = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        default=0,
        verbose_name='Qiymətləndirmə (0-10)'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaradılma tarixi')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Yenilənmə tarixi')

    class Meta:
        verbose_name = 'Şagird Sinif Qeydiyyatı'
        verbose_name_plural = 'Şagird Sinif Qeydiyyətləri'
        unique_together = [('student', 'class_assigned')]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.student.get_full_name()} - {self.class_assigned.name}'

    @property
    def attendance_label(self):
        return dict(self.ATTENDANCE_CHOICES).get(self.attendance_status, '--------')


class Reklam(models.Model):
    ad = models.CharField(max_length=100, verbose_name='Ad', blank=False, null=False)
    soyad = models.CharField(max_length=100, verbose_name='Soyad', blank=False, null=False)
    ixtisas_fenni = models.CharField(max_length=250, verbose_name='İxtisas / Fənn', blank=False, null=False)
    sekil = models.ImageField(upload_to='reklamlar/', verbose_name='Şəkil', blank=True, null=True)
    haqqinda_melumat = models.TextField(verbose_name='Haqqında məlumat', blank=True, null=True)
    telefon_nomresi = models.CharField(max_length=30, verbose_name='Telefon nömrəsi', blank=True, null=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reklamlar',
        verbose_name='Sahib'
    )
    xususi_reklam = models.BooleanField(default=False, verbose_name='Xüsusi Reklam')
    yaradilma_tarixi = models.DateTimeField(auto_now_add=True, verbose_name='Yaradılma tarixi')
    yenilenme_tarixi = models.DateTimeField(auto_now=True, verbose_name='Yenilənmə tarixi')

    class Meta:
        verbose_name = 'Reklam'
        verbose_name_plural = 'Reklamlar'
        ordering = ['-xususi_reklam', '-yenilenme_tarixi']

    def __str__(self):
        return f'{self.ad} {self.soyad} - {self.ixtisas_fenni}'

    def save(self, *args, **kwargs):
        if self.ad:
            self.ad = capitalize_az(self.ad)
        if self.soyad:
            self.soyad = capitalize_az(self.soyad)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('core:reklam_detail', kwargs={'pk': self.pk})


class Feedback(models.Model):
    message = models.TextField(
        max_length=1500,
        verbose_name='Rəy və təklif'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='feedbacks',
        verbose_name='Yaradan'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Yaradılma tarixi'
    )

    class Meta:
        verbose_name = 'Rəy və Təklif'
        verbose_name_plural = 'Rəylər və Təkliflər'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.message[:50]}...' if len(self.message) > 50 else self.message
