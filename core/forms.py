from django import forms
from django.db import models as django_models
from django.db.models import Q as Q_ORM
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit, Row, Column
from .models import (
    User, Class, Student, Lesson, Attendance, Reklam, Feedback,
    ClassRosterEntry, StudentClassEnrollment, capitalize_az
)


def _apply_bootstrap_classes(form):
    for field_name, field in form.fields.items():
        if isinstance(field.widget, forms.HiddenInput):
            continue
        classes = field.widget.attrs.get('class', '')
        if isinstance(field.widget, (forms.Select, forms.SelectMultiple, forms.RadioSelect)):
            widget_class = 'form-select'
        elif isinstance(field.widget, forms.CheckboxInput):
            widget_class = 'form-check-input'
        else:
            widget_class = 'form-control'
        if widget_class not in classes:
            field.widget.attrs['class'] = f'{classes} {widget_class}'.strip()
        if field.required and not isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs.setdefault('required', True)


def _managed_teacher_ids(user):
    """Reuse the request user's managed-teacher set across forms and views."""
    managed_ids = getattr(user, '_managed_teacher_ids', None)
    if managed_ids is None:
        managed_ids = set(User.objects.filter(
            created_by=user, staff=User.ROLE_MUALLIM, is_active=True
        ).values_list('pk', flat=True))
        user._managed_teacher_ids = managed_ids
    return managed_ids


class UserRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'staff', 'subject', 'reklam_icazesi', 'password1', 'password2']

    def clean_first_name(self):
        return capitalize_az(self.cleaned_data.get('first_name', ''))

    def clean_last_name(self):
        return capitalize_az(self.cleaned_data.get('last_name', ''))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.is_superuser:
            self.fields['staff'].choices = (
                (User.ROLE_KURS_INZIBATCHISI, 'Kurs-inzibatçısı'),
                (User.ROLE_MUALLIM, 'Müəllim'),
            )
        else:
            self.fields['staff'].choices = ((User.ROLE_MUALLIM, 'Müəllim'),)
            self.fields['staff'].initial = User.ROLE_MUALLIM
            self.fields['staff'].widget = forms.HiddenInput()
        self.fields['username'].label = 'İstifadəçi adı'
        self.fields['email'].label = 'E-poçt'
        self.fields['first_name'].label = 'Ad'
        self.fields['last_name'].label = 'Soyad'
        self.fields['staff'].label = 'Vəzifə'
        self.fields['subject'].label = 'Fənn'
        self.fields['reklam_icazesi'].label = 'Reklam icazəsi'
        self.fields['password1'].label = 'Şifrə'
        self.fields['password2'].label = 'Şifrəni təstiqləyin'
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        staff_field = 'staff'
        if user and not user.is_superuser:
            staff_layout = Field('staff', type='hidden')
        else:
            staff_layout = Column('staff', css_class='form-group col-md-4 mb-3')
        self.helper.layout = Layout(
            Row(
                Column('username', css_class='form-group col-md-6 mb-3'),
                Column('email', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('first_name', css_class='form-group col-md-6 mb-3'),
                Column('last_name', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                staff_layout,
                Column('subject', css_class='form-group col-md-4 mb-3'),
                Column('reklam_icazesi', css_class='form-group col-md-4 mb-3'),
            ),
            Row(
                Column('password1', css_class='form-group col-md-6 mb-3'),
                Column('password2', css_class='form-group col-md-6 mb-3'),
            ),
            Submit('submit', 'Yadda saxla', css_class='btn btn-primary w-100')
        )


class UserUpdateForm(UserChangeForm):
    password = None

    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name',
            'staff', 'subject', 'reklam_icazesi',
            'teacher_creation_limit', 'lesson_link',
            'activation_date', 'deactivation_date',
            'is_active'
        ]
        widgets = {
            'activation_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'deactivation_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def clean_first_name(self):
        return capitalize_az(self.cleaned_data.get('first_name', ''))

    def clean_last_name(self):
        return capitalize_az(self.cleaned_data.get('last_name', ''))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        instance = kwargs.get('instance')
        is_self_staff_edit = (
            user
            and instance is not None
            and instance.pk is not None
            and user.pk == instance.pk
        )

        is_teacher_editor = (
            user
            and not user.is_superuser
            and (
                (not getattr(user, 'is_course_admin', False) and getattr(user, 'is_teacher', False))
                or (getattr(user, 'is_course_admin', False) and is_self_staff_edit)
            )
        )

        if is_teacher_editor:
            allowed = ['first_name', 'last_name', 'subject', 'lesson_link']
            for fname in list(self.fields.keys()):
                if fname not in allowed:
                    del self.fields[fname]
            self.fields['first_name'].label = 'Ad'
            self.fields['last_name'].label = 'Soyad'
            self.fields['subject'].label = 'Fənn'
            self.fields['lesson_link'].label = 'Xüsusi Dərs Linki'
            _apply_bootstrap_classes(self)
            self.helper = FormHelper()
            self.helper.form_method = 'post'
            self.helper.layout = Layout(
                Row(
                    Column('first_name', css_class='form-group col-md-6 mb-3'),
                    Column('last_name', css_class='form-group col-md-6 mb-3'),
                ),
                Row(
                    Column('subject', css_class='form-group col-md-6 mb-3'),
                    Column('lesson_link', css_class='form-group col-md-6 mb-3'),
                ),
                Submit('submit', 'Yadda saxla', css_class='btn btn-primary w-100')
            )
            return

        if user and user.is_superuser:
            self.fields['staff'].choices = (
                (User.ROLE_KURS_INZIBATCHISI, 'Kurs-inzibatçısı'),
                (User.ROLE_MUALLIM, 'Müəllim'),
                (User.ROLE_DIGER, 'Digər'),
            )
        else:
            self.fields['staff'].choices = ((User.ROLE_MUALLIM, 'Müəllim'),)
            for f in ('teacher_creation_limit', 'activation_date', 'deactivation_date', 'staff'):
                if f in self.fields:
                    self.fields[f].widget = forms.HiddenInput()
        self.fields['username'].label = 'İstifadəçi adı'
        self.fields['email'].label = 'E-poçt'
        self.fields['first_name'].label = 'Ad'
        self.fields['last_name'].label = 'Soyad'
        self.fields['staff'].label = 'Vəzifə'
        self.fields['subject'].label = 'Fənn'
        self.fields['reklam_icazesi'].label = 'Reklam icazəsi'
        self.fields['teacher_creation_limit'].label = 'Müəllim yaratma limiti'
        self.fields['lesson_link'].label = 'Xüsusi Dərs Linki'
        self.fields['activation_date'].label = 'Aktivləşmə tarixi'
        self.fields['deactivation_date'].label = 'Deaktivləşmə tarixi'
        self.fields['is_active'].label = 'Aktiv hesab'
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('username', css_class='form-group col-md-6 mb-3'),
                Column('email', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('first_name', css_class='form-group col-md-6 mb-3'),
                Column('last_name', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('staff', css_class='form-group col-md-4 mb-3'),
                Column('subject', css_class='form-group col-md-4 mb-3'),
                Column('reklam_icazesi', css_class='form-group col-md-4 mb-3'),
            ),
            Row(
                Column('teacher_creation_limit', css_class='form-group col-md-4 mb-3'),
                Column('lesson_link', css_class='form-group col-md-8 mb-3'),
            ),
            Row(
                Column('activation_date', css_class='form-group col-md-6 mb-3'),
                Column('deactivation_date', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('is_active', css_class='form-group col-md-6 mb-3'),
            ),
            Submit('submit', 'Yadda saxla', css_class='btn btn-primary w-100')
        )


class ClassForm(forms.ModelForm):
    class Meta:
        model = Class
        fields = ['name', 'teacher']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].label = 'Sinif adı'
        self.fields['teacher'].label = 'Müəllim'
        if user and not user.is_superuser:
            if user.is_teacher and not user.is_course_admin:
                self.fields['teacher'].queryset = User.objects.filter(pk=user.pk)
                self.fields['teacher'].initial = user.pk
                self.fields['teacher'].widget = forms.HiddenInput()
            elif user.is_course_admin:
                self.fields['teacher'].queryset = User.objects.filter(
                    Q_ORM(created_by=user, staff=User.ROLE_MUALLIM) |
                    Q_ORM(pk=user.pk, staff=User.ROLE_KURS_INZIBATCHISI)
                )
            else:
                self.fields['teacher'].queryset = User.objects.filter(
                    Q_ORM(staff=User.ROLE_MUALLIM) |
                    Q_ORM(pk=user.pk, staff=User.ROLE_KURS_INZIBATCHISI)
                )
        else:
            self.fields['teacher'].queryset = User.objects.filter(
                staff__in=(User.ROLE_MUALLIM, User.ROLE_KURS_INZIBATCHISI)
            )
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('name', css_class='form-group col-md-6 mb-3'),
                Column('teacher', css_class='form-group col-md-6 mb-3'),
            ),
            Submit('submit', 'Yadda saxla', css_class='btn btn-primary w-100')
        )


class StudentForm(forms.ModelForm):
    class Meta:
        model = ClassRosterEntry
        fields = ['full_name', 'current_class']

    def clean_full_name(self):
        return capitalize_az(self.cleaned_data.get('full_name', ''))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['full_name'].label = 'Tam adı'
        self.fields['current_class'].label = 'Cari sinif'
        if user and not user.is_superuser:
            if user.is_teacher or user.is_course_admin:
                if user.is_course_admin:
                    managed_teacher_ids = _managed_teacher_ids(user)
                    self.fields['current_class'].queryset = Class.objects.filter(
                        Q_ORM(teacher=user) | Q_ORM(created_by=user)
                        | Q_ORM(teacher_id__in=managed_teacher_ids)
                    ).distinct()
                else:
                    self.fields['current_class'].queryset = Class.objects.filter(teacher=user)
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('full_name', css_class='form-group col-md-6 mb-3'),
                Column('current_class', css_class='form-group col-md-6 mb-3'),
            ),
            Submit('submit', 'Yadda saxla', css_class='btn btn-primary w-100')
        )


class LoginForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'İstifadəçi adı'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Şifrə'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'İstifadəçi adı'
        self.fields['password'].label = 'Şifrə'
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Field('username', css_class='mb-3'),
            Field('password', css_class='mb-3'),
            Submit('submit', 'Daxil ol', css_class='btn btn-primary w-100')
        )


class StudentLoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Şagird istifadəçi adı'}),
        label='Şagird istifadəçi adı'
    )
    password = forms.CharField(
        max_length=150,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Şagird şifrəsi'}),
        label='Şagird şifrəsi'
    )

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')
        if username and password:
            try:
                student = Student.objects.get(username=username, password=password)
                if not student.activity_status:
                    raise forms.ValidationError(
                        'Hesabınızın istifadə müddəti bitmişdir. '
                        'Xahiş edirik sistem inzibatçısı ilə əlaqə saxlayın.'
                    )
            except Student.DoesNotExist:
                raise forms.ValidationError('Yanlış istifadəçi adı və ya şifrə.')
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Field('username', css_class='mb-3'),
            Field('password', css_class='mb-3'),
            Submit('submit', 'Şagird kimi daxil ol', css_class='btn btn-primary w-100')
        )


class NewStudentForm(forms.ModelForm):
    selected_classes = forms.ModelMultipleChoiceField(
        queryset=Class.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Siniflər'
    )

    class Meta:
        model = Student
        fields = ['firstname', 'lastname', 'activity_status']

    def clean_firstname(self):
        return capitalize_az(self.cleaned_data.get('firstname', ''))

    def clean_lastname(self):
        return capitalize_az(self.cleaned_data.get('lastname', ''))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['firstname'].label = 'Ad'
        self.fields['lastname'].label = 'Soyad'
        self.fields['activity_status'].label = 'Aktivlik statusu'
        self.fields['firstname'].required = True
        self.fields['lastname'].required = True
        if user:
            if user.is_superuser:
                self.fields['selected_classes'].queryset = Class.objects.select_related('teacher').all()
            elif user.is_course_admin:
                managed_teacher_ids = _managed_teacher_ids(user)
                self.fields['selected_classes'].queryset = Class.objects.filter(
                    Q_ORM(teacher=user) | Q_ORM(created_by=user)
                    | Q_ORM(teacher_id__in=managed_teacher_ids)
                ).distinct()
            elif user.is_teacher:
                self.fields['selected_classes'].queryset = Class.objects.filter(teacher=user)
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('firstname', css_class='form-group col-md-6 mb-3'),
                Column('lastname', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('activity_status', css_class='form-group col-md-12 mb-3'),
            ),
            Row(
                Column('selected_classes', css_class='form-group col-md-12 mb-3'),
            ),
            Submit('submit', 'Şagirdi yarat', css_class='btn btn-primary w-100')
        )


class StudentEnrollmentForm(forms.Form):
    existing_student = forms.ModelChoiceField(
        queryset=Student.objects.none(),
        required=False,
        label='Mövcud şagird (opsional)',
        help_text='Sinfi olmayan və ya başqa sinifdəki şagirdləri seçin'
    )
    firstname = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Şagirdin adı'}),
        label='Ad'
    )
    lastname = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Şagirdin soyadı'}),
        label='Soyad'
    )
    target_class = forms.ModelChoiceField(
        queryset=Class.objects.none(),
        label='Hədəf sinif'
    )

    def clean_firstname(self):
        return capitalize_az(self.cleaned_data.get('firstname', ''))

    def clean_lastname(self):
        return capitalize_az(self.cleaned_data.get('lastname', ''))

    def clean(self):
        cleaned_data = super().clean()
        existing_student = cleaned_data.get('existing_student')
        target_class = cleaned_data.get('target_class')
        needs_creation = False

        if existing_student:
            student = existing_student
            if not student.activity_status:
                raise forms.ValidationError(
                    'Hesabın istifadə müddəti bitmişdir. '
                    'Xahiş edirik sistem inzibatçısı ilə əlaqə saxlayın.'
                )
        else:
            firstname = (cleaned_data.get('firstname') or '').strip()
            lastname = (cleaned_data.get('lastname') or '').strip()
            if not firstname or not lastname:
                raise forms.ValidationError(
                    'Zəhmət olmasa ya mövcud şagirdi seçin, '
                    'ya da yeni şagird üçün ad və soyad daxil edin.'
                )

            candidates = Student.objects.filter(
                firstname__iexact=firstname,
                lastname__iexact=lastname
            )
            candidate_list = list(candidates[:2])
            candidate_count = len(candidate_list)
            if candidate_count > 1:
                raise forms.ValidationError(
                    'Eyni ad və soyada sahib bir neçə şagird tapıldı. '
                    'Zəhmət olmasa yuxarıdakı "Mövcud şagird" sahəsindən düzgün olanı seçin.'
                )
            elif candidate_count == 1:
                student = candidate_list[0]
                if not student.activity_status:
                    raise forms.ValidationError(
                        'Hesabın istifadə müddəti bitmişdir. '
                        'Xahiş edirik sistem inzibatçısı ilə əlaqə saxlayın.'
                    )
            else:
                needs_creation = True
                cleaned_data['create_firstname'] = firstname
                cleaned_data['create_lastname'] = lastname
                student = None

        if target_class and student and student.classes.filter(pk=target_class.pk).exists():
            raise forms.ValidationError('Şagird artıq bu sinifdə qeydiyyatlıdır.')

        cleaned_data['student'] = student
        cleaned_data['needs_creation'] = needs_creation
        cleaned_data['is_new_student'] = needs_creation
        return cleaned_data

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_user = user
        if user:
            if user.is_superuser:
                self.fields['existing_student'].queryset = (
                    Student.objects.select_related('created_by')
                    .order_by('lastname', 'firstname')
                )
                self.fields['target_class'].queryset = Class.objects.select_related('teacher').all()
            elif user.is_course_admin:
                managed_teacher_ids = _managed_teacher_ids(user)
                course_student_q = (
                    Q_ORM(created_by=user)
                    | Q_ORM(created_by_id__in=managed_teacher_ids)
                    | Q_ORM(classes__teacher=user)
                    | Q_ORM(classes__teacher_id__in=managed_teacher_ids)
                )
                self.fields['existing_student'].queryset = (
                    Student.objects.filter(course_student_q)
                    .select_related('created_by')
                    .order_by('lastname', 'firstname')
                    .distinct()
                )
                self.fields['target_class'].queryset = Class.objects.filter(
                    Q_ORM(teacher=user) | Q_ORM(created_by=user)
                    | Q_ORM(teacher_id__in=managed_teacher_ids)
                ).distinct()
            elif user.is_teacher:
                teacher_student_q = (
                    Q_ORM(created_by=user) | Q_ORM(classes__teacher=user)
                )
                self.fields['existing_student'].queryset = (
                    Student.objects.filter(teacher_student_q)
                    .select_related('created_by')
                    .order_by('lastname', 'firstname')
                    .distinct()
                )
                self.fields['target_class'].queryset = Class.objects.filter(teacher=user)
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('existing_student', css_class='form-group col-md-12 mb-3'),
            ),
            Row(
                Column('firstname', css_class='form-group col-md-6 mb-3'),
                Column('lastname', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('target_class', css_class='form-group col-md-12 mb-3'),
            ),
            Submit('submit', 'Şagirdi sinifə daxil et', css_class='btn btn-primary w-100')
        )


class DirectStudentEnrollForm(forms.Form):
    target_class = forms.ModelChoiceField(
        queryset=Class.objects.none(),
        label='Hədəf sinif'
    )

    def __init__(self, *args, user=None, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_user = user
        self.current_student = student
        if user:
            if user.is_superuser:
                self.fields['target_class'].queryset = Class.objects.select_related('teacher').all()
            elif user.is_course_admin:
                managed_teacher_ids = _managed_teacher_ids(user)
                self.fields['target_class'].queryset = Class.objects.filter(
                    Q_ORM(teacher=user) | Q_ORM(created_by=user)
                    | Q_ORM(teacher_id__in=managed_teacher_ids)
                ).distinct()
            elif user.is_teacher:
                self.fields['target_class'].queryset = Class.objects.filter(teacher=user)
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('target_class', css_class='form-group col-md-12 mb-3'),
            ),
            Submit('submit', 'Şagirdi sinifə təyin et', css_class='btn btn-primary w-100')
        )

    def clean_target_class(self):
        target_class = self.cleaned_data.get('target_class')
        if target_class and self.current_student:
            if self.current_student.classes.filter(pk=target_class.pk).exists():
                raise forms.ValidationError('Şagird artıq bu sinifdə qeydiyyatlıdır.')
        return target_class


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ['class_assigned', 'title_topic', 'date', 'start_time', 'end_time']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['class_assigned'].label = 'Sinif'
        self.fields['title_topic'].label = 'Mövzu'
        self.fields['date'].label = 'Tarix'
        self.fields['start_time'].label = 'Başlama vaxtı'
        self.fields['end_time'].label = 'Bitmə vaxtı'
        if user and not user.is_superuser:
            if user.is_course_admin:
                managed_teacher_ids = _managed_teacher_ids(user)
                self.fields['class_assigned'].queryset = Class.objects.filter(
                    Q_ORM(created_by=user) | Q_ORM(teacher=user)
                    | Q_ORM(teacher_id__in=managed_teacher_ids)
                ).distinct()
            elif user.is_teacher:
                self.fields['class_assigned'].queryset = Class.objects.filter(teacher=user)
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('class_assigned', css_class='form-group col-md-12 mb-3'),
            ),
            Row(
                Column('title_topic', css_class='form-group col-md-12 mb-3'),
            ),
            Row(
                Column('date', css_class='form-group col-md-4 mb-3'),
                Column('start_time', css_class='form-group col-md-4 mb-3'),
                Column('end_time', css_class='form-group col-md-4 mb-3'),
            ),
            Submit('submit', 'Yadda saxla', css_class='btn btn-primary w-100')
        )


class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['status']
        widgets = {
            'status': forms.RadioSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].label = ''
        _apply_bootstrap_classes(self)


class StudentUpdateForm(forms.ModelForm):
    attendance_grades = forms.IntegerField(
        min_value=0,
        max_value=10,
        initial=0,
        required=False,
        label='Davamiyyət Qiyməti (0-10)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '10', 'placeholder': '0-10 arası qiymət'})
    )

    class Meta:
        model = Student
        fields = ['firstname', 'lastname', 'attendance_grades', 'activity_status']

    def clean_firstname(self):
        return capitalize_az(self.cleaned_data.get('firstname', ''))

    def clean_lastname(self):
        return capitalize_az(self.cleaned_data.get('lastname', ''))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['firstname'].label = 'Ad'
        self.fields['lastname'].label = 'Soyad'
        self.fields['attendance_grades'].label = 'Davamiyyət Qiyməti (0-10)'
        self.fields['activity_status'].label = 'Aktivlik statusu'
        self.fields['firstname'].required = True
        self.fields['lastname'].required = True
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('firstname', css_class='form-group col-md-6 mb-3'),
                Column('lastname', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('attendance_grades', css_class='form-group col-md-6 mb-3'),
                Column('activity_status', css_class='form-group col-md-6 mb-3'),
            ),
            Submit('submit', 'Yadda saxla', css_class='btn btn-primary w-100')
        )


class ReklamForm(forms.ModelForm):
    MAX_IMAGE_SIZE_MB = 6

    class Meta:
        model = Reklam
        fields = ['ad', 'soyad', 'ixtisas_fenni', 'sekil', 'haqqinda_melumat', 'telefon_nomresi']
        widgets = {
            'haqqinda_melumat': forms.Textarea(attrs={'rows': 5}),
        }

    def clean_ad(self):
        value = (self.cleaned_data.get('ad') or '').strip()
        if not value:
            raise forms.ValidationError('Bu sahə tələb olunur.')
        return capitalize_az(value)

    def clean_soyad(self):
        value = (self.cleaned_data.get('soyad') or '').strip()
        if not value:
            raise forms.ValidationError('Bu sahə tələb olunur.')
        return capitalize_az(value)

    def clean_ixtisas_fenni(self):
        value = (self.cleaned_data.get('ixtisas_fenni') or '').strip()
        if not value:
            raise forms.ValidationError('Bu sahə tələb olunur.')
        return value

    def clean_sekil(self):
        image = self.cleaned_data.get('sekil')
        if image:
            max_bytes = self.MAX_IMAGE_SIZE_MB * 1024 * 1024
            if hasattr(image, 'size') and image.size > max_bytes:
                raise forms.ValidationError(
                    f'Şəkilin ölçüsü maksimum {self.MAX_IMAGE_SIZE_MB} MB ola bilər. '
                    f'Hazırkı ölçü: {round(image.size / (1024 * 1024), 2)} MB.'
                )
        return image

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ad'].label = 'Ad'
        self.fields['soyad'].label = 'Soyad'
        self.fields['ixtisas_fenni'].label = 'İxtisas / Fənn'
        self.fields['sekil'].label = 'Şəkil'
        self.fields['haqqinda_melumat'].label = 'Haqqında məlumat'
        self.fields['telefon_nomresi'].label = 'Telefon nömrəsi'
        self.fields['ad'].required = True
        self.fields['soyad'].required = True
        self.fields['ixtisas_fenni'].required = True
        self.fields['ad'].widget.attrs['placeholder'] = 'Ad daxil edin'
        self.fields['soyad'].widget.attrs['placeholder'] = 'Soyad daxil edin'
        self.fields['ixtisas_fenni'].widget.attrs['placeholder'] = 'Fənn və ya ixtisas'
        self.fields['telefon_nomresi'].widget.attrs['placeholder'] = '+994 ...'
        self.fields['haqqinda_melumat'].widget.attrs['placeholder'] = 'Qısa təqdimat yazın'
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('ad', css_class='form-group col-md-6 mb-3'),
                Column('soyad', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('ixtisas_fenni', css_class='form-group col-md-12 mb-3'),
            ),
            Row(
                Column('sekil', css_class='form-group col-md-6 mb-3'),
                Column('telefon_nomresi', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('haqqinda_melumat', css_class='form-group col-md-12 mb-3'),
            ),
        )


class TeacherApplicationForm(forms.Form):
    ad = forms.CharField(
        max_length=100,
        label='Ad',
        widget=forms.TextInput(attrs={'placeholder': 'Adınızı daxil edin'})
    )
    soyad = forms.CharField(
        max_length=100,
        label='Soyad',
        widget=forms.TextInput(attrs={'placeholder': 'Soyadınızı daxil edin'})
    )
    username = forms.CharField(
        max_length=150,
        label='İstifadəçi adı (Tələb olunan)',
        help_text='Hesab üçün istifadəçi adı',
        widget=forms.TextInput(attrs={'placeholder': 'musteri123'})
    )
    fenn = forms.CharField(
        max_length=200,
        label='Fənn',
        widget=forms.TextInput(attrs={'placeholder': 'Riyaziyyat, Fizika, Azərbaycan dili və s.'})
    )
    email = forms.EmailField(
        label='E-poçt',
        widget=forms.EmailInput(attrs={'placeholder': 'ornek@email.com'})
    )

    def clean_ad(self):
        return capitalize_az(self.cleaned_data.get('ad', ''))

    def clean_soyad(self):
        return capitalize_az(self.cleaned_data.get('soyad', ''))

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if username and not all(c.isalnum() or c in '_.-' for c in username):
            raise forms.ValidationError(
                'İstifadəçi adı yalnız hərf, rəqəm və _ . - simvolları ola bilər.'
            )
        return username

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Row(
                Column('ad', css_class='form-group col-md-6 mb-3'),
                Column('soyad', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('username', css_class='form-group col-md-12 mb-3'),
            ),
            Row(
                Column('fenn', css_class='form-group col-md-6 mb-3'),
                Column('email', css_class='form-group col-md-6 mb-3'),
            ),
        )


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={
                'rows': 6,
                'maxlength': 1500,
                'placeholder': 'Rəy və ya təklifinizi buraya yazın...',
            }),
        }

    def clean_message(self):
        message = self.cleaned_data.get('message', '').strip()
        if len(message) < 10:
            raise forms.ValidationError(
                'Rəy və ya təklif ən az 10 simvol olmalıdır.'
            )
        return message

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['message'].label = 'Rəy və Təklif'
        _apply_bootstrap_classes(self)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Field('message', css_class='mb-3'),
        )
