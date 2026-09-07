from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Class, Student, Lesson, Attendance, Reklam,
    ClassRosterEntry, StudentClassEnrollment
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username', 'email', 'first_name', 'last_name',
        'get_staff_label', 'teacher_creation_limit',
        'subject', 'reklam_icazesi', 'is_active', 'is_superuser',
        'created_by', 'activation_date', 'deactivation_date'
    )
    list_filter = ('staff', 'reklam_icazesi', 'is_active', 'is_superuser')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'subject')
    ordering = ('-is_superuser', '-staff', 'username')
    readonly_fields = ('last_login', 'date_joined')

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Şəxsi Məlumat', {'fields': ('first_name', 'last_name', 'email')}),
        ('Vəzifə Məlumatı', {'fields': (
            'staff', 'subject', 'reklam_icazesi',
            'teacher_creation_limit', 'lesson_link',
        )}),
        ('Hesab Müddəti', {'fields': (
            'activation_date', 'deactivation_date',
        )}),
        ('Mənsubiyyət', {'fields': ('created_by',)}),
        ('İcazələr', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Vacib tarixlər', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'password1', 'password2',
                'staff', 'subject', 'reklam_icazesi',
                'teacher_creation_limit', 'lesson_link',
                'activation_date', 'deactivation_date',
                'email', 'first_name', 'last_name',
                'created_by', 'is_active',
            ),
        }),
    )

    def get_staff_label(self, obj):
        return obj.get_role_display()
    get_staff_label.short_description = 'Vəzifə'
    get_staff_label.admin_order_field = 'staff'

    def has_module_permission(self, request):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not user.can_access_django_admin:
            return False
        return super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not user.can_access_django_admin:
            return False
        return super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not user.can_access_django_admin:
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not user.can_access_django_admin:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not user.can_access_django_admin:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'teacher', 'student_count', 'created_by', 'created_at', 'updated_at')
    list_filter = ('teacher', 'created_by')
    search_fields = ('name', 'teacher__username', 'teacher__first_name', 'teacher__last_name')
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        'username', 'firstname', 'lastname',
        'attendance_grades', 'activity_status',
        'created_by', 'created_at'
    )
    list_filter = ('activity_status', 'created_by')
    search_fields = ('username', 'firstname', 'lastname')
    ordering = ('lastname', 'firstname')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ClassRosterEntry)
class ClassRosterEntryAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 'current_class', 'participants',
        'created_by', 'created_at', 'updated_at'
    )
    list_filter = ('current_class', 'participants', 'created_by')
    search_fields = ('full_name', 'current_class__name')
    ordering = ('full_name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StudentClassEnrollment)
class StudentClassEnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        'student', 'class_assigned', 'attendance_status',
        'evaluation_grade', 'created_at'
    )
    list_filter = ('class_assigned', 'attendance_status')
    search_fields = (
        'student__firstname', 'student__lastname',
        'student__username', 'class_assigned__name'
    )
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = (
        'title_topic', 'class_assigned', 'date',
        'start_time', 'end_time', 'created_by', 'created_at'
    )
    list_filter = ('class_assigned', 'date', 'created_by')
    search_fields = ('title_topic', 'class_assigned__name')
    ordering = ('-date', '-start_time')
    readonly_fields = ('created_at',)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = (
        'lesson', 'student', 'status',
        'created_at', 'updated_at'
    )
    list_filter = ('status', 'lesson__class_assigned', 'lesson__date')
    search_fields = ('student__full_name', 'lesson__title_topic')
    ordering = ('-lesson__date', '-lesson__start_time', 'student__full_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Reklam)
class ReklamAdmin(admin.ModelAdmin):
    list_display = (
        'ad', 'soyad', 'ixtisas_fenni', 'owner',
        'xususi_reklam_badge', 'telefon_nomresi', 'yaradilma_tarixi'
    )
    list_filter = ('ixtisas_fenni', 'xususi_reklam')
    search_fields = ('ad', 'soyad', 'ixtisas_fenni', 'owner__username')
    ordering = ('-xususi_reklam', '-yenilenme_tarixi')
    readonly_fields = ('yaradilma_tarixi', 'yenilenme_tarixi')
    fieldsets = (
        ('Ümumi Məlumat', {
            'fields': ('ad', 'soyad', 'ixtisas_fenni', 'owner', 'telefon_nomresi')
        }),
        ('Xüsusi', {
            'fields': ('xususi_reklam',),
            'description': 'Reklamı xüsusi (öne çıxarılan) kimi işarələmək üçün bu sahəni işarələyin.'
        }),
        ('Məzmun', {
            'fields': ('sekil', 'haqqinda_melumat')
        }),
        ('Vacib Tarixlər', {
            'fields': readonly_fields,
            'classes': ('collapse',)
        }),
    )

    def xususi_reklam_badge(self, obj):
        if obj.xususi_reklam:
            return '⭐ Xüsusi'
        return '—'
    xususi_reklam_badge.short_description = 'Xüsusi'
    xususi_reklam_badge.admin_order_field = 'xususi_reklam'
