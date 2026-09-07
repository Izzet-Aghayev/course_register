import threading
import traceback

from django.shortcuts import render, redirect, get_object_or_404, reverse
from django.utils import timezone
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.core.cache import cache
from functools import wraps

from .models import (
    User, Class, Student, Lesson, Attendance, Reklam, Feedback,
    ClassRosterEntry, StudentClassEnrollment,
)
from .forms import (
    LoginForm, StudentLoginForm, UserRegistrationForm, UserUpdateForm,
    ClassForm, StudentForm, NewStudentForm, StudentUpdateForm, StudentEnrollmentForm,
    DirectStudentEnrollForm,
    LessonForm, AttendanceForm, ReklamForm, TeacherApplicationForm, FeedbackForm,
)
from .notifications import (
    notify_teacher_application,
    notify_teacher_limit_exceeded,
    notify_feedback,
)
import logging

logger = logging.getLogger(__name__)


ACCOUNT_EXPIRED_MESSAGE = (
    'Hesabınızın istifadə müddəti bitmişdir. '
    'Xahiş edirik sistem inzibatçısı ilə əlaqə saxlayın.'
)

LIMIT_EXCEEDED_MESSAGE = (
    'Siz artıq müəllim yaratmaq limitinə çatmısınız. '
    'Limiti artırmaq üçün xahiş edirik inzibatçı ilə əlaqə saxlayın.'
)

LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 10
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 300
PUBLIC_SUBMISSION_MAX_ATTEMPTS = 5
PUBLIC_SUBMISSION_WINDOW_SECONDS = 600
NOTIFIED_USERS_CACHE_TTL = 86400


def _get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def _login_attempt_key(request, username=''):
    ip = _get_client_ip(request)
    safe_uname = (username or '').strip().lower() or 'any'
    return f'login_fail:ip:{ip}:user:{safe_uname}'


def _check_login_rate_limit(request, username=''):
    key = _login_attempt_key(request, username)
    current = cache.get(key, 0)
    return current < LOGIN_RATE_LIMIT_MAX_ATTEMPTS


def _record_login_failure(request, username=''):
    key = _login_attempt_key(request, username)
    try:
        cache.add(key, 0, LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        cache.incr(key)
    except Exception as exc:
        logger.warning('Login rate-limit cache write failed: %s', exc)


def _record_login_success(request, username=''):
    key = _login_attempt_key(request, username)
    try:
        cache.delete(key)
    except Exception as exc:
        logger.warning('Login rate-limit cache delete failed: %s', exc)


def _allow_public_submission(request, endpoint):
    key = f'public_submit:{endpoint}:ip:{_get_client_ip(request)}'
    try:
        if cache.get(key, 0) >= PUBLIC_SUBMISSION_MAX_ATTEMPTS:
            return False
        cache.add(key, 0, PUBLIC_SUBMISSION_WINDOW_SECONDS)
        cache.incr(key)
        return True
    except Exception as exc:
        logger.warning('Public submission rate-limit cache write failed: %s', exc)
        return True


def _was_limit_notified(user):
    if user is None or not getattr(user, 'pk', None):
        return False
    key = f'limit_notified:user:{user.pk}'
    return bool(cache.get(key, False))


def _mark_limit_notified(user):
    if user is None or not getattr(user, 'pk', None):
        return
    key = f'limit_notified:user:{user.pk}'
    try:
        cache.set(key, True, NOTIFIED_USERS_CACHE_TTL)
    except Exception as exc:
        logger.warning('Limit-notified cache write failed: %s', exc)


def _clear_limit_notified(user):
    if user is None or not getattr(user, 'pk', None):
        return
    key = f'limit_notified:user:{user.pk}'
    try:
        cache.delete(key)
    except Exception as exc:
        logger.warning('Limit-notified cache delete failed: %s', exc)


def is_admin(user):
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or getattr(user, 'is_course_admin', False)


def is_teacher_or_admin(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if getattr(user, 'is_teacher', False):
        return True
    if getattr(user, 'is_course_admin', False):
        return True
    return False


def get_session_role(request):
    if request.session.get('student_id'):
        return 'student'
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        if user.is_superuser:
            return 'admin'
        if getattr(user, 'is_course_admin', False):
            return 'course_admin'
        if getattr(user, 'is_teacher', False):
            return 'teacher'
    return None


def get_current_student(request):
    student_id = request.session.get('student_id')
    if student_id:
        try:
            student = Student.objects.get(pk=student_id, activity_status=True)
            return student
        except Student.DoesNotExist:
            request.session.pop('student_id', None)
            return None
    return None


def any_authenticated_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.session.get('student_id'):
            return view_func(request, *args, **kwargs)
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            return view_func(request, *args, **kwargs)
        return redirect('core:login')
    return _wrapped


def teacher_or_admin_required(view_func):
    @login_required
    @user_passes_test(is_teacher_or_admin)
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return _wrapped


def build_common_context(request, extra=None):
    ctx = dict(extra or {})
    ctx['current_path'] = request.path
    is_htmx = request.META.get('HTTP_HX_REQUEST', '') == 'true'
    request.htmx = is_htmx
    ctx['is_htmx'] = is_htmx
    ctx['base_template'] = 'htmx_partial.html' if is_htmx else 'base.html'
    try:
        from django.urls import resolve, Resolver404
        match = resolve(request.path_info)
        if match and match.url_name:
            PUBLIC_URLS = {
                'landing_page', 'reklam_list', 'reklam_detail',
                'login', 'student_login',
                'teacher_application_submit',
            }
            if match.url_name in PUBLIC_URLS:
                ctx['is_public_page'] = True
    except Exception:
        pass
    if request.path_info in ('/', '/login/', '/student/login/'):
        ctx['is_public_page'] = True
    return ctx


def _owner_filter_for_user(user, owner_field_name='created_by', include_teacher_self=False):
    if user.is_superuser:
        return Q()
    base = Q(**{f'{owner_field_name}': user})
    if include_teacher_self:
        base = base | Q(teacher=user)
    return base


def _get_managed_teacher_ids(user):
    if user.is_superuser:
        return None
    if not getattr(user, 'is_course_admin', False):
        return set()
    if hasattr(user, '_managed_teacher_ids'):
        return user._managed_teacher_ids
    user._managed_teacher_ids = set(User.objects.filter(
        created_by=user, staff=User.ROLE_MUALLIM, is_active=True
    ).values_list('pk', flat=True))
    return user._managed_teacher_ids


def _course_admin_class_q(user, managed_teacher_ids=None):
    if user.is_superuser:
        return Q()
    if managed_teacher_ids is None:
        managed_teacher_ids = _get_managed_teacher_ids(user)
    return (
        Q(created_by=user)
        | Q(teacher=user)
        | Q(teacher_id__in=managed_teacher_ids)
    )


def _course_admin_lesson_q(user, managed_teacher_ids=None):
    if user.is_superuser:
        return Q()
    if managed_teacher_ids is None:
        managed_teacher_ids = _get_managed_teacher_ids(user)
    return (
        Q(created_by=user)
        | Q(class_assigned__teacher=user)
        | Q(class_assigned__teacher_id__in=managed_teacher_ids)
    )


def _course_admin_created_q(user, via_field, managed_teacher_ids=None):
    if user.is_superuser:
        return Q()
    if managed_teacher_ids is None:
        managed_teacher_ids = _get_managed_teacher_ids(user)
    return (
        Q(**{f'{via_field}': user})
        | Q(**{f'{via_field}_id__in': managed_teacher_ids})
    )


def landing_page(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    teacher_application_form = TeacherApplicationForm()
    try:
        total_muellimler = User.objects.filter(is_active=True, staff=User.ROLE_MUALLIM).count()
    except Exception:
        total_muellimler = 0
    try:
        total_sinifler = Class.objects.count()
    except Exception:
        total_sinifler = 0
    try:
        total_shagirdler = Student.objects.count()
    except Exception:
        total_shagirdler = 0
    try:
        total_reklamlar = Reklam.objects.count()
    except Exception:
        total_reklamlar = 0
    try:
        reklamlar = list(
            Reklam.objects.select_related('owner')
            .order_by('-xususi_reklam', '-yenilenme_tarixi')[:8]
        )
    except Exception:
        reklamlar = []

    context = build_common_context(request, {
        'teacher_application_form': teacher_application_form,
        'total_muellimler': total_muellimler,
        'total_sinifler': total_sinifler,
        'total_shagirdler': total_shagirdler,
        'total_reklamlar': total_reklamlar,
        'reklamlar': reklamlar,
    })
    return render(request, 'landing_page.html', context)


def login_view(request):
    form = LoginForm()
    if request.method == 'POST':
        form = LoginForm(request.POST)
        username = (form.data.get('username') or '').strip()
        if not _check_login_rate_limit(request, username):
            messages.error(
                request,
                'Həddindən artıq səhv giriş cəhdi. Zəhmət olmasa bir neçə dəqiqə sonra yenidən cəhd edin.'
            )
            context = build_common_context(request, {'form': form})
            return render(request, 'auth/login.html', context)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user:
                if not user.can_access_django_admin and request.path.startswith('/admin'):
                    messages.error(request, 'İnzibatçi paneli üçün icazəniz yoxdur.')
                    return redirect('core:dashboard')
                if not user.is_active:
                    _record_login_failure(request, username)
                    messages.error(request, ACCOUNT_EXPIRED_MESSAGE)
                    return redirect('core:login')
                if not user.is_superuser and user.is_account_expired():
                    user.is_active = False
                    user.save(update_fields=['is_active'])
                    _record_login_failure(request, username)
                    messages.error(request, ACCOUNT_EXPIRED_MESSAGE)
                    return redirect('core:login')
                auth_login(request, user)
                _record_login_success(request, username)
                messages.success(request, f'Xoş gəlmisiniz, {user.get_full_name() or user.username}!')
                return redirect('core:dashboard')
            else:
                _record_login_failure(request, username)
                messages.error(request, 'Yanlış istifadəçi adı və ya şifrə.')
        else:
            _record_login_failure(request, (request.POST.get('username') or '').strip())
    context = build_common_context(request, {'form': form})
    return render(request, 'auth/login.html', context)


def student_login_view(request):
    form = StudentLoginForm()
    if request.method == 'POST':
        form = StudentLoginForm(request.POST)
        username = (form.data.get('username') or '').strip()
        if not _check_login_rate_limit(request, username):
            messages.error(
                request,
                'Həddindən artıq səhv giriş cəhdi. Zəhmət olmasa bir neçə dəqiqə sonra yenidən cəhd edin.'
            )
            context = build_common_context(request, {'form': form, 'is_student_login': True})
            return render(request, 'auth/login.html', context)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            try:
                student = Student.objects.get(username=username, password=password)
                if not student.activity_status:
                    _record_login_failure(request, username)
                    messages.error(request, ACCOUNT_EXPIRED_MESSAGE)
                    return redirect('core:student_login')
                request.session['student_id'] = student.pk
                _record_login_success(request, username)
                messages.success(request, f'Xoş gəlmisiniz, {student.get_full_name()}!')
                return redirect('core:dashboard')
            except Student.DoesNotExist:
                _record_login_failure(request, username)
                messages.error(request, 'Yanlış istifadəçi adı və ya şifrə.')
        else:
            _record_login_failure(request, (request.POST.get('username') or '').strip())
    context = build_common_context(request, {'form': form, 'is_student_login': True})
    return render(request, 'auth/login.html', context)


@login_required
def logout_view(request):
    auth_logout(request)
    messages.success(request, 'Sistemdən uğurla çıxış edildi.')
    return redirect('core:login')


def student_logout_view(request):
    if 'student_id' in request.session:
        del request.session['student_id']
    messages.success(request, 'Sistemdən uğurla çıxış edildi.')
    return redirect('core:student_login')


@any_authenticated_required
def dashboard(request):
    role = get_session_role(request)
    if role == 'student':
        student = get_current_student(request)
        student_classes = student.classes.select_related('teacher').all()
        total_classes = student_classes.count()
        total_students = Student.objects.filter(classes__in=student_classes).distinct().count()
        total_lessons = Lesson.objects.filter(class_assigned__in=student_classes).count()
        enrollments = StudentClassEnrollment.objects.filter(student=student).select_related('class_assigned__teacher')
        classes_with_enrollments = []
        for enr in enrollments:
            classes_with_enrollments.append({
                'class_obj': enr.class_assigned,
                'total_students': enr.class_assigned.student_count,
                'attendance_status': enr.attendance_label,
                'evaluation_grade': enr.evaluation_grade,
            })
        total_reklamlar = Reklam.objects.count()
        context = build_common_context(request, {
            'total_classes': total_classes,
            'total_students': total_students,
            'total_lessons': total_lessons,
            'total_reklamlar': total_reklamlar,
            'avg_grade': 0,
            'classes_with_counts': classes_with_enrollments,
            'recent_users': [],
        })
        return render(request, 'dashboard.html', context)

    user = request.user
    if user.is_superuser:
        total_teachers = User.objects.filter(staff=User.ROLE_MUALLIM).count()
        total_course_admins = User.objects.filter(staff=User.ROLE_KURS_INZIBATCHISI).count()
        total_classes = Class.objects.count()
        total_students = Student.objects.count()
        total_lessons = Lesson.objects.count()
        classes = Class.objects.select_related('teacher').all()
        recent_users = User.objects.exclude(pk=user.pk)[:5]
    elif user.is_course_admin:
        managed_teacher_ids = _get_managed_teacher_ids(user)
        total_teachers = len(managed_teacher_ids) if managed_teacher_ids else User.objects.filter(
            created_by=user, staff=User.ROLE_MUALLIM
        ).count()
        class_q = _course_admin_class_q(user, managed_teacher_ids)
        total_classes = Class.objects.filter(class_q).distinct().count()
        class_ids = Class.objects.filter(class_q).values_list('id', flat=True)
        total_students = Student.objects.filter(
            Q(classes__id__in=class_ids) | _course_admin_created_q(user, 'created_by', managed_teacher_ids)
        ).distinct().count()
        total_lessons = Lesson.objects.filter(_course_admin_lesson_q(user, managed_teacher_ids)).count()
        classes = Class.objects.filter(class_q).select_related('teacher').distinct()
        recent_users = User.objects.filter(
            Q(created_by=user) | Q(created_by_id__in=managed_teacher_ids)
        )[:5] if managed_teacher_ids else User.objects.filter(created_by=user)[:5]
    else:
        total_teachers = 0
        total_classes = Class.objects.filter(teacher=user).count()
        total_students = Student.objects.filter(classes__teacher=user).distinct().count()
        total_lessons = Lesson.objects.filter(class_assigned__teacher=user).count()
        classes = Class.objects.filter(teacher=user)
        recent_users = User.objects.none()

    classes_qs = classes.annotate(total_students=Count('students'))
    classes_with_counts = []
    for c in classes_qs:
        classes_with_counts.append({
            'class_obj': c,
            'total_students': c.total_students,
        })

    avg_students_per_class = round(total_students / total_classes) if total_classes > 0 else 0
    total_reklamlar = Reklam.objects.count() if user.is_superuser else user.get_active_reklam_count()
    teacher_creation_limit = getattr(user, 'teacher_creation_limit', 0) if hasattr(user, 'is_course_admin') and user.is_course_admin else None
    is_course_admin = getattr(user, 'is_course_admin', False) if not user.is_superuser else False

    context = build_common_context(request, {
        'total_teachers': total_teachers,
        'total_classes': total_classes,
        'total_students': total_students,
        'total_lessons': total_lessons,
        'total_reklamlar': total_reklamlar,
        'avg_students_per_class': avg_students_per_class,
        'classes_with_counts': classes_with_counts,
        'recent_users': list(recent_users),
        'teacher_creation_limit': teacher_creation_limit,
        'is_course_admin': is_course_admin,
    })
    return render(request, 'dashboard.html', context)


@login_required
@user_passes_test(is_admin)
def teacher_list(request):
    query = request.GET.get('q', '')
    user = request.user
    if user.is_superuser:
        teachers = User.objects.filter(
            staff__in=(User.ROLE_MUALLIM, User.ROLE_KURS_INZIBATCHISI)
        ).select_related('created_by')
    else:
        teachers = User.objects.filter(created_by=user, staff=User.ROLE_MUALLIM).select_related('created_by')
    if query:
        teachers = teachers.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(subject__icontains=query)
        )
    active_ads = Count('reklamlar')
    teachers = teachers.annotate(active_reklam_count=active_ads).order_by('last_name', 'first_name')
    paginator = Paginator(teachers, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    context = build_common_context(request, {
        'teachers': page_obj,
        'page_obj': page_obj,
        'query': query,
    })
    return render(request, 'teachers/list.html', context)


@login_required
@user_passes_test(is_admin)
def teacher_create(request):
    user = request.user
    if user.is_course_admin:
        current_limit = getattr(user, 'teacher_creation_limit', 0)
        if current_limit <= 0:
            messages.error(request, LIMIT_EXCEEDED_MESSAGE)
            if not _was_limit_notified(user):
                _mark_limit_notified(user)
                try:
                    notify_teacher_limit_exceeded(user)
                except Exception:
                    pass
            return redirect('core:teacher_list')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST, user=user)
        if form.is_valid():
            if user.is_course_admin:
                if user.teacher_creation_limit <= 0:
                    messages.error(request, LIMIT_EXCEEDED_MESSAGE)
                    if not _was_limit_notified(user):
                        _mark_limit_notified(user)
                        try:
                            notify_teacher_limit_exceeded(user)
                        except Exception:
                            pass
                    return redirect('core:teacher_list')

            new_user = form.save(commit=False)
            if new_user.staff in (User.ROLE_MUALLIM, User.ROLE_KURS_INZIBATCHISI):
                new_user.is_staff = True
            new_user.created_by = user
            new_user.save()

            if user.is_course_admin:
                user.teacher_creation_limit = max(0, user.teacher_creation_limit - 1)
                user.save(update_fields=['teacher_creation_limit'])

            messages.success(request, f'Müəllim {new_user.username} uğurla yaradıldı!')
            return redirect('core:teacher_list')
    else:
        form = UserRegistrationForm(user=user)
    context = build_common_context(request, {'form': form, 'action': 'Əlavə et'})
    return render(request, 'teachers/form.html', context)


@login_required
def teacher_update(request, pk):
    user = request.user
    is_self_teacher = False

    if user.is_superuser:
        teacher = get_object_or_404(User, pk=pk, staff__in=(User.ROLE_MUALLIM, User.ROLE_KURS_INZIBATCHISI))
    elif getattr(user, 'is_course_admin', False):
        if pk == user.pk:
            teacher = get_object_or_404(User, pk=pk, staff__in=(User.ROLE_MUALLIM, User.ROLE_KURS_INZIBATCHISI))
            is_self_teacher = True
        else:
            teacher = User.objects.filter(
                pk=pk, created_by=user, staff=User.ROLE_MUALLIM
            ).first()
            if teacher is None:
                raise PermissionDenied('Bu müəllim profilini redaktə etmək üçün icazəniz yoxdur.')
    elif getattr(user, 'is_teacher', False) and user.pk == pk:
        teacher = get_object_or_404(User, pk=pk, staff=User.ROLE_MUALLIM)
        is_self_teacher = True
    else:
        raise PermissionDenied('Bu əməliyyatı yerinə yetirmək üçün icazəniz yoxdur.')

    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=teacher, user=user)
        if form.is_valid():
            updated = form.save()
            if updated.staff in (User.ROLE_MUALLIM, User.ROLE_KURS_INZIBATCHISI):
                if not updated.is_staff:
                    updated.is_staff = True
                    updated.save(update_fields=['is_staff'])
            if is_self_teacher:
                messages.success(request, 'Profiliniz uğurla yeniləndi!')
                return redirect('core:dashboard')
            messages.success(request, f'Müəllim {teacher.username} uğurla yeniləndi!')
            return redirect('core:teacher_list')
    else:
        form = UserUpdateForm(instance=teacher, user=user)
    context = build_common_context(request, {
        'form': form,
        'action': 'Redaktə et',
        'teacher': teacher,
        'is_self_teacher': is_self_teacher,
    })
    return render(request, 'teachers/form.html', context)


@login_required
@user_passes_test(is_admin)
def teacher_delete(request, pk):
    user = request.user
    if user.is_superuser:
        teacher = get_object_or_404(User, pk=pk, staff__in=(User.ROLE_MUALLIM, User.ROLE_KURS_INZIBATCHISI))
    else:
        teacher_qs = User.objects.filter(
            pk=pk, created_by=user, staff=User.ROLE_MUALLIM
        )
        if not teacher_qs.exists():
            managed_ids = _get_managed_teacher_ids(user)
            teacher_qs = User.objects.filter(
                pk=pk, pk__in=managed_ids, staff=User.ROLE_MUALLIM
            )
        teacher = teacher_qs.first()
        if teacher is None:
            raise PermissionDenied('Bu müəllim profilini silmək üçün icazəniz yoxdur.')
    if request.method == 'POST':
        username = teacher.username
        was_created_by_current = (
            user.is_course_admin
            and teacher.created_by_id == user.pk
            and teacher.staff == User.ROLE_MUALLIM
        )
        teacher.delete()
        if was_created_by_current:
            user.teacher_creation_limit = user.teacher_creation_limit + 1
            user.save(update_fields=['teacher_creation_limit'])
            _clear_limit_notified(user)
        messages.success(request, f'Müəllim {username} uğurla silindi!')
        return redirect('core:teacher_list')
    context = build_common_context(request, {'teacher': teacher})
    return render(request, 'teachers/delete.html', context)


@any_authenticated_required
def class_list(request):
    role = get_session_role(request)
    query = request.GET.get('q', '')
    user = request.user

    if role == 'student':
        student = get_current_student(request)
        classes = student.classes.select_related('teacher').all()
        if query:
            classes = classes.filter(
                Q(name__icontains=query) |
                Q(teacher__username__icontains=query) |
                Q(teacher__first_name__icontains=query) |
                Q(teacher__last_name__icontains=query)
            )
        classes_qs = classes.annotate(total_students=Count('students')).order_by('name')
        paginator = Paginator(classes_qs, 12)
        page_obj = paginator.get_page(request.GET.get('page', 1))
        context = build_common_context(request, {
            'classes': page_obj,
            'page_obj': page_obj,
            'query': query,
        })
        return render(request, 'classes/list.html', context)
    else:
        if user.is_superuser:
            classes = Class.objects.select_related('teacher').all()
        elif user.is_course_admin:
            class_q = _course_admin_class_q(user)
            classes = Class.objects.filter(class_q).select_related('teacher').distinct()
        else:
            classes = Class.objects.filter(teacher=user).select_related('teacher')
        if query:
            classes = classes.filter(
                Q(name__icontains=query) |
                Q(teacher__username__icontains=query) |
                Q(teacher__first_name__icontains=query) |
                Q(teacher__last_name__icontains=query)
            )
        classes_qs = classes.annotate(total_students=Count('students')).order_by('name')
        paginator = Paginator(classes_qs, 12)
        page_obj = paginator.get_page(request.GET.get('page', 1))
        context = build_common_context(request, {
            'classes': page_obj,
            'page_obj': page_obj,
            'query': query,
        })
        return render(request, 'classes/list.html', context)


@teacher_or_admin_required
def class_create(request):
    user = request.user
    if request.method == 'POST':
        form = ClassForm(request.POST, user=user)
        if form.is_valid():
            cls = form.save(commit=False)
            cls.created_by = user
            cls.save()
            messages.success(request, f'Sinif {cls.name} uğurla yaradıldı!')
            return redirect('core:class_list')
    else:
        form = ClassForm(user=user)
    context = build_common_context(request, {'form': form, 'action': 'Əlavə et'})
    return render(request, 'classes/form.html', context)


@teacher_or_admin_required
def class_update(request, pk):
    user = request.user
    if user.is_superuser:
        cls = get_object_or_404(Class, pk=pk)
    elif user.is_course_admin:
        class_q = _course_admin_class_q(user)
        cls = get_object_or_404(Class.objects.filter(class_q).distinct(), pk=pk)
    else:
        cls = get_object_or_404(Class, pk=pk, teacher=user)
    if request.method == 'POST':
        form = ClassForm(request.POST, instance=cls, user=user)
        if form.is_valid():
            cls = form.save()
            messages.success(request, f'Sinif {cls.name} uğurla yeniləndi!')
            return redirect('core:class_list')
    else:
        form = ClassForm(instance=cls, user=user)
    context = build_common_context(request, {'form': form, 'action': 'Redaktə et', 'class_obj': cls})
    return render(request, 'classes/form.html', context)


@teacher_or_admin_required
def class_delete(request, pk):
    user = request.user
    if user.is_superuser:
        cls = get_object_or_404(Class, pk=pk)
    elif user.is_course_admin:
        class_q = _course_admin_class_q(user)
        cls = get_object_or_404(Class.objects.filter(class_q).distinct(), pk=pk)
    else:
        cls = get_object_or_404(Class, pk=pk, teacher=user)
    if request.method == 'POST':
        name = cls.name
        cls.delete()
        messages.success(request, f'Sinif {name} uğurla silindi!')
        return redirect('core:class_list')
    context = build_common_context(request, {'class_obj': cls})
    return render(request, 'classes/delete.html', context)


@any_authenticated_required
def class_detail(request, pk):
    role = get_session_role(request)
    user = request.user
    if role == 'student':
        student = get_current_student(request)
        cls = get_object_or_404(
            Class.objects.filter(students=student).select_related('teacher'),
            pk=pk
        )
        students = cls.students.all()
        lessons = cls.lessons.all()
        student_count = students.count()
        enrollment = StudentClassEnrollment.objects.filter(student=student, class_assigned=cls).first()
        context = build_common_context(request, {
            'class_obj': cls,
            'students': students,
            'lessons': lessons,
            'student_count': student_count,
            'my_grade': enrollment.evaluation_grade if enrollment else None,
            'my_attendance': enrollment.attendance_label if enrollment else None,
        })
        return render(request, 'classes/detail.html', context)

    if user.is_superuser:
        cls = get_object_or_404(Class.objects.select_related('teacher'), pk=pk)
    elif user.is_course_admin:
        class_q = _course_admin_class_q(user)
        cls = get_object_or_404(
            Class.objects.filter(class_q).distinct().select_related('teacher'),
            pk=pk
        )
    else:
        cls = get_object_or_404(Class.objects.filter(teacher=user).select_related('teacher'), pk=pk)
    students = cls.students.prefetch_related('classes', 'classes__teacher').all()
    lessons = cls.lessons.select_related('class_assigned__teacher').all()
    student_count = students.count()
    context = build_common_context(request, {
        'class_obj': cls,
        'students': students,
        'lessons': lessons,
        'student_count': student_count,
    })
    return render(request, 'classes/detail.html', context)


@teacher_or_admin_required
def student_list(request):
    user = request.user
    query = request.GET.get('q', '')
    class_filter = request.GET.get('class', '')
    if user.is_superuser:
        students = Student.objects.prefetch_related('classes', 'classes__teacher').all()
    elif user.is_course_admin:
        managed_teacher_ids = _get_managed_teacher_ids(user)
        student_q = (
            _course_admin_created_q(user, 'created_by', managed_teacher_ids)
            | Q(classes__teacher=user)
            | Q(classes__teacher_id__in=managed_teacher_ids)
        )
        students = Student.objects.filter(student_q
        ).prefetch_related('classes', 'classes__teacher').distinct()
    else:
        students = Student.objects.filter(
            classes__teacher=user
        ).prefetch_related('classes', 'classes__teacher').distinct()
    if query:
        students = students.filter(
            Q(firstname__icontains=query) |
            Q(lastname__icontains=query) |
            Q(username__icontains=query) |
            Q(classes__name__icontains=query)
        ).distinct()
    if class_filter:
        students = students.filter(classes__pk=class_filter).distinct()
    if user.is_superuser:
        class_options = Class.objects.all()
    elif user.is_course_admin:
        class_options = Class.objects.filter(_course_admin_class_q(user, managed_teacher_ids)).distinct()
    else:
        class_options = Class.objects.filter(teacher=user)
    students = students.order_by('lastname', 'firstname', 'username')
    paginator = Paginator(students, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    context = build_common_context(request, {
        'students': page_obj,
        'page_obj': page_obj,
        'query': query,
        'class_filter': class_filter,
        'class_options': class_options,
    })
    return render(request, 'students/list.html', context)


@teacher_or_admin_required
def student_account_list(request):
    user = request.user
    query = request.GET.get('q', '').strip()
    class_query = request.GET.get('class_q', '').strip()

    if class_query:
        if 'sinfi mövcud olmayan' in class_query.lower() or 'mövcud olmayan' in class_query.lower():
            if user.is_superuser:
                unassigned_students = Student.objects.filter(classes=None).order_by('lastname', 'firstname')
            elif user.is_course_admin:
                managed_teacher_ids = _get_managed_teacher_ids(user)
                unassigned_students = Student.objects.filter(
                    _course_admin_created_q(user, 'created_by', managed_teacher_ids), classes=None
                ).order_by('lastname', 'firstname').distinct()
            else:
                unassigned_students = Student.objects.none()
        else:
            unassigned_students = Student.objects.none()
    else:
        if user.is_superuser:
            unassigned_students = Student.objects.filter(classes=None).order_by('lastname', 'firstname')
        elif user.is_course_admin:
            managed_teacher_ids = _get_managed_teacher_ids(user)
            unassigned_students = Student.objects.filter(
                _course_admin_created_q(user, 'created_by', managed_teacher_ids), classes=None
            ).order_by('lastname', 'firstname').distinct()
        else:
            unassigned_students = Student.objects.none()

    if query:
        unassigned_students = unassigned_students.filter(
            Q(firstname__icontains=query) |
            Q(lastname__icontains=query) |
            Q(username__icontains=query)
        ).distinct()

    if user.is_superuser:
        classes = Class.objects.prefetch_related('students').all().order_by('name')
    elif user.is_course_admin:
        class_q = _course_admin_class_q(user, managed_teacher_ids)
        classes = Class.objects.filter(class_q
        ).prefetch_related('students').order_by('name').distinct()
    else:
        classes = Class.objects.filter(teacher=user).prefetch_related('students').order_by('name')

    if class_query:
        classes = classes.filter(name__icontains=class_query)

    class_groups = []
    if query:
        for cls in classes:
            cls_students = [
                s for s in cls.students.all()
                if (query in (s.firstname or ''))
                or (query in (s.lastname or ''))
                or (query in (s.username or ''))
            ]
            cls_students.sort(key=lambda s: (s.lastname or '', s.firstname or ''))
            if cls_students:
                class_groups.append({
                    'class': cls,
                    'students': cls_students,
                    'count': len(cls_students),
                })
    else:
        for cls in classes:
            cls_students = sorted(
                cls.students.all(),
                key=lambda s: (s.lastname or '', s.firstname or '')
            )
            class_groups.append({
                'class': cls,
                'students': cls_students,
                'count': len(cls_students),
            })

    total_student_count = unassigned_students.count() + sum(cg['count'] for cg in class_groups)

    context = build_common_context(request, {
        'unassigned_students': unassigned_students,
        'class_groups': class_groups,
        'query': query,
        'class_q': class_query,
        'total_student_count': total_student_count,
    })
    return render(request, 'students/credentials_list.html', context)


@teacher_or_admin_required
def new_student_create(request):
    user = request.user
    if request.method == 'POST':
        form = NewStudentForm(request.POST, user=user)
        if form.is_valid():
            student = form.save(commit=False)
            student.created_by = user
            student.save()
            selected_classes = form.cleaned_data.get('selected_classes', [])
            for cls in selected_classes:
                StudentClassEnrollment.objects.get_or_create(
                    student=student,
                    class_assigned=cls,
                    defaults={'attendance_status': 'i/e', 'evaluation_grade': 0}
                )
            messages.success(
                request,
                f'Şagird {student.get_full_name()} uğurla yaradıldı! '
                f'İstifadəçi adı: {student.username}, Şifrə: {student.password}'
            )
            return redirect('core:student_account_list')
    else:
        form = NewStudentForm(user=user)
    context = build_common_context(request, {'form': form, 'action': 'Yeni şagird yarat'})
    return render(request, 'students/new_student_form.html', context)


@teacher_or_admin_required
def student_enroll(request):
    user = request.user
    if request.method == 'POST':
        form = StudentEnrollmentForm(request.POST, user=user)
        if form.is_valid():
            needs_creation = form.cleaned_data.get('needs_creation', False)
            target_class = form.cleaned_data['target_class']
            with transaction.atomic():
                if needs_creation:
                    firstname = form.cleaned_data.get('create_firstname', '')
                    lastname = form.cleaned_data.get('create_lastname', '')
                    create_kwargs = {
                        'firstname': firstname,
                        'lastname': lastname,
                        'activity_status': True,
                        'created_by': user,
                    }
                    student = Student.objects.create(**create_kwargs)
                    is_new_student = True
                else:
                    student = form.cleaned_data['student']
                    is_new_student = False

                StudentClassEnrollment.objects.get_or_create(
                    student=student,
                    class_assigned=target_class,
                    defaults={'attendance_status': 'i/e', 'evaluation_grade': 0}
                )
            if is_new_student:
                messages.success(
                    request,
                    f'Şagird {student.get_full_name()} uğurla yaradıldı və "{target_class.name}" sinifinə daxil edildi! '
                    f'İstifadəçi adı: {student.username}, Şifrə: {student.password}'
                )
            else:
                messages.success(
                    request,
                    f'{student.get_full_name()} adlı şagird "{target_class.name}" sinifinə uğurla daxil edildi!'
                )
            return redirect('core:student_account_list')
    else:
        form = StudentEnrollmentForm(user=user)
    context = build_common_context(request, {'form': form, 'action': 'Şagird daxil edin'})
    return render(request, 'students/enroll_form.html', context)


@teacher_or_admin_required
def student_assign_class(request, student_id):
    user = request.user
    if user.is_superuser:
        student = get_object_or_404(Student, pk=student_id)
    elif user.is_course_admin:
        managed_teacher_ids = _get_managed_teacher_ids(user)
        student_q = (
            _course_admin_created_q(user, 'created_by', managed_teacher_ids)
            | Q(classes__teacher=user)
            | Q(classes__teacher_id__in=managed_teacher_ids)
        )
        student = get_object_or_404(
            Student.objects.filter(student_q).distinct(), pk=student_id
        )
    else:
        teacher_student_q = Q(created_by=user) | Q(classes__teacher=user)
        student = get_object_or_404(
            Student.objects.filter(teacher_student_q).distinct(), pk=student_id
        )

    if not student.activity_status:
        messages.error(request, 'Şagirdin hesabı deaktivdir. Sinifə təyin etmək üçün əvvəlcə hesabı aktivləşdirin.')
        return redirect('core:student_account_list')

    if request.method == 'POST':
        form = DirectStudentEnrollForm(request.POST, user=user, student=student)
        if form.is_valid():
            target_class = form.cleaned_data['target_class']
            StudentClassEnrollment.objects.create(
                student=student,
                class_assigned=target_class,
                attendance_status='i/e',
                evaluation_grade=0
            )
            messages.success(
                request,
                f'{student.get_full_name()} adlı şagird "{target_class.name}" sinifinə uğurla təyin edildi!'
            )
            return redirect('core:student_account_list')
    else:
        form = DirectStudentEnrollForm(user=user, student=student)

    context = build_common_context(request, {
        'form': form,
        'action': 'Şagirdi sinifə təyin et',
        'student': student,
    })
    return render(request, 'students/assign_class_form.html', context)


student_direct_enroll = student_assign_class


@teacher_or_admin_required
def student_update(request, pk):
    user = request.user
    if user.is_superuser:
        student = get_object_or_404(Student, pk=pk)
    elif user.is_course_admin:
        managed_teacher_ids = _get_managed_teacher_ids(user)
        student_q = (
            _course_admin_created_q(user, 'created_by', managed_teacher_ids)
            | Q(classes__teacher=user)
            | Q(classes__teacher_id__in=managed_teacher_ids)
        )
        student = get_object_or_404(
            Student.objects.filter(student_q).distinct(),
            pk=pk
        )
    else:
        student = get_object_or_404(
            Student.objects.filter(classes__teacher=user).distinct(),
            pk=pk
        )
    if request.method == 'POST':
        form = StudentUpdateForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, f'Şagird {student.get_full_name()} uğurla yeniləndi!')
            return redirect('core:student_list')
    else:
        form = StudentUpdateForm(instance=student)
    context = build_common_context(request, {'form': form, 'action': 'Redaktə et', 'student': student})
    return render(request, 'students/form.html', context)


@teacher_or_admin_required
def student_delete(request, pk):
    user = request.user
    if user.is_superuser:
        student = get_object_or_404(Student, pk=pk)
        owned_class_ids = list(Class.objects.values_list('id', flat=True))
        teacher_owned_roster_classes = owned_class_ids
    elif user.is_course_admin:
        managed_teacher_ids = _get_managed_teacher_ids(user)
        student_q = (
            _course_admin_created_q(user, 'created_by', managed_teacher_ids)
            | Q(classes__teacher=user)
            | Q(classes__teacher_id__in=managed_teacher_ids)
        )
        student = get_object_or_404(
            Student.objects.filter(student_q).distinct(),
            pk=pk
        )
        own_class_q = _course_admin_class_q(user, managed_teacher_ids)
        owned_class_ids = list(Class.objects.filter(own_class_q).values_list('id', flat=True).distinct())
    else:
        student = get_object_or_404(
            Student.objects.filter(classes__teacher=user).distinct(),
            pk=pk
        )
        owned_class_ids = list(Class.objects.filter(teacher=user).values_list('id', flat=True))

    if request.method == 'POST':
        name = student.get_full_name()
        all_student_class_ids = list(student.classes.values_list('id', flat=True))
        shared_class_ids = [cid for cid in all_student_class_ids if cid not in owned_class_ids]
        only_owned_classes = len(shared_class_ids) == 0

        if user.is_superuser or only_owned_classes:
            student.delete()
            messages.success(request, f'Şagird {name} uğurla silindi!')
        else:
            with transaction.atomic():
                StudentClassEnrollment.objects.filter(
                    student=student,
                    class_assigned_id__in=owned_class_ids
                ).delete()
            messages.success(
                request,
                f'Şagird {name} məxsus siniflərdən çıxarıldı. '
                f'Başqa müəllimlərin siniflərindəki üzvüyü qorundu.'
            )
        return redirect('core:student_list')
    context = build_common_context(request, {'student': student})
    return render(request, 'students/delete.html', context)


@teacher_or_admin_required
def roster_list(request):
    user = request.user
    query = request.GET.get('q', '')
    class_filter = request.GET.get('class', '')
    if user.is_superuser:
        roster_entries = ClassRosterEntry.objects.select_related('current_class', 'current_class__teacher').all()
    elif user.is_course_admin:
        managed_teacher_ids = _get_managed_teacher_ids(user)
        roster_q = (
            _course_admin_created_q(user, 'created_by', managed_teacher_ids)
            | Q(current_class__teacher=user)
            | Q(current_class__teacher_id__in=managed_teacher_ids)
        )
        roster_entries = ClassRosterEntry.objects.filter(roster_q
        ).select_related('current_class', 'current_class__teacher').distinct()
    else:
        roster_entries = ClassRosterEntry.objects.filter(
            current_class__teacher=user
        ).select_related('current_class', 'current_class__teacher')
    if query:
        roster_entries = roster_entries.filter(
            Q(full_name__icontains=query) |
            Q(current_class__name__icontains=query)
        )
    if class_filter:
        roster_entries = roster_entries.filter(current_class__pk=class_filter)
    if user.is_superuser:
        class_options = Class.objects.all()
    elif user.is_course_admin:
        class_options = Class.objects.filter(_course_admin_class_q(user, managed_teacher_ids)).distinct()
    else:
        class_options = Class.objects.filter(teacher=user)
    roster_entries = roster_entries.order_by('-created_at', 'pk')
    paginator = Paginator(roster_entries, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    context = build_common_context(request, {
        'roster_entries': page_obj,
        'page_obj': page_obj,
        'query': query,
        'class_filter': class_filter,
        'class_options': class_options,
    })
    return render(request, 'students/roster_list.html', context)


@teacher_or_admin_required
def roster_create(request):
    user = request.user
    if request.method == 'POST':
        form = StudentForm(request.POST, user=user)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.created_by = user
            entry.save()
            messages.success(request, f'Qeydiyyat {entry.full_name} uğurla yaradıldı!')
            return redirect('core:roster_list')
    else:
        form = StudentForm(user=user)
    context = build_common_context(request, {'form': form, 'action': 'Əlavə et'})
    return render(request, 'students/form.html', context)


@teacher_or_admin_required
def roster_update(request, pk):
    user = request.user
    if user.is_superuser:
        entry = get_object_or_404(ClassRosterEntry, pk=pk)
    elif user.is_course_admin:
        managed_teacher_ids = _get_managed_teacher_ids(user)
        roster_q = (
            _course_admin_created_q(user, 'created_by', managed_teacher_ids)
            | Q(current_class__teacher=user)
            | Q(current_class__teacher_id__in=managed_teacher_ids)
        )
        entry = get_object_or_404(
            ClassRosterEntry.objects.filter(roster_q).distinct(),
            pk=pk
        )
    else:
        entry = get_object_or_404(ClassRosterEntry, pk=pk, current_class__teacher=user)
    if request.method == 'POST':
        form = StudentForm(request.POST, instance=entry, user=user)
        if form.is_valid():
            entry = form.save()
            messages.success(request, f'Qeydiyyat {entry.full_name} uğurla yeniləndi!')
            return redirect('core:roster_list')
    else:
        form = StudentForm(instance=entry, user=user)
    context = build_common_context(request, {'form': form, 'action': 'Redaktə et', 'entry': entry})
    return render(request, 'students/form.html', context)


@teacher_or_admin_required
def roster_delete(request, pk):
    user = request.user
    if user.is_superuser:
        entry = get_object_or_404(ClassRosterEntry, pk=pk)
    elif user.is_course_admin:
        managed_teacher_ids = _get_managed_teacher_ids(user)
        roster_q = (
            _course_admin_created_q(user, 'created_by', managed_teacher_ids)
            | Q(current_class__teacher=user)
            | Q(current_class__teacher_id__in=managed_teacher_ids)
        )
        entry = get_object_or_404(
            ClassRosterEntry.objects.filter(roster_q).distinct(),
            pk=pk
        )
    else:
        entry = get_object_or_404(ClassRosterEntry, pk=pk, current_class__teacher=user)
    if request.method == 'POST':
        name = entry.full_name
        entry.delete()
        messages.success(request, f'Qeydiyyat {name} uğurla silindi!')
        return redirect('core:roster_list')
    context = build_common_context(request, {'entry': entry})
    return render(request, 'students/delete.html', context)


@any_authenticated_required
def lesson_list(request):
    role = get_session_role(request)
    class_filter = request.GET.get('class', '')
    user = request.user
    if role == 'student':
        student = get_current_student(request)
        if not student:
            return redirect('core:student_login')
        student_class_ids = list(student.classes.values_list('id', flat=True))
        lessons_qs = Lesson.objects.filter(
            class_assigned__in=student_class_ids
        ).select_related('class_assigned', 'class_assigned__teacher').order_by('date', 'start_time', 'id')
        class_options = student.classes.all()
        if class_filter:
            lessons_qs = lessons_qs.filter(class_assigned__pk=class_filter)

        status_labels = dict(Attendance.STATUS_CHOICES)
        att_map = {}
        lessons_list = list(lessons_qs)
        if lessons_list:
            attendances = Attendance.objects.filter(
                lesson__in=lessons_list,
                student=student,
            )
            for record in attendances:
                att_map[record.lesson_id] = record.status

        lesson_items = []
        for lesson in lessons_list:
            code = att_map.get(lesson.pk, '')
            lesson.personal_status = code
            lesson.personal_status_label = status_labels.get(code, '--------') or '--------'
            lesson.personal_is_grade = code.isdigit() and 0 <= int(code) <= 10
            lesson.student_delay_seconds = lesson.student_delay_seconds_remaining
            lesson.student_can_join = (
                not lesson.is_expired and lesson.is_active and bool(lesson.lesson_link)
                and lesson.student_delay_seconds == 0
            )
            lesson.student_btn_disabled = (
                lesson.is_expired or not lesson.is_active or not lesson.lesson_link
                or lesson.student_delay_seconds > 0
            )
            lesson_items.append(lesson)
        lessons = lesson_items
    else:
        if user.is_superuser:
            lessons = Lesson.objects.select_related('class_assigned', 'class_assigned__teacher').all().order_by('date', 'start_time', 'id')
            class_options = Class.objects.all()
        elif user.is_course_admin:
            lesson_q = _course_admin_lesson_q(user)
            class_q = _course_admin_class_q(user)
            lessons = Lesson.objects.filter(lesson_q
            ).select_related('class_assigned', 'class_assigned__teacher').order_by('date', 'start_time', 'id').distinct()
            class_options = Class.objects.filter(class_q).distinct()
        else:
            lessons = Lesson.objects.filter(
                class_assigned__teacher=user
            ).select_related('class_assigned', 'class_assigned__teacher').order_by('date', 'start_time', 'id')
            class_options = Class.objects.filter(teacher=user)
        if class_filter:
            lessons = lessons.filter(class_assigned__pk=class_filter)

    context = build_common_context(request, {
        'lessons': lessons,
        'class_filter': class_filter,
        'class_options': class_options,
    })
    if not isinstance(lessons, list):
        paginator = Paginator(lessons, 25)
        page_obj = paginator.get_page(request.GET.get('page', 1))
        context['lessons'] = page_obj
        context['page_obj'] = page_obj
    else:
        paginator = Paginator(lessons, 25)
        page_obj = paginator.get_page(request.GET.get('page', 1))
        context['lessons'] = page_obj
        context['page_obj'] = page_obj
    return render(request, 'lessons/list.html', context)


@teacher_or_admin_required
def lesson_create(request):
    user = request.user
    if request.method == 'POST':
        form = LessonForm(request.POST, user=user)
        if form.is_valid():
            with transaction.atomic():
                lesson = form.save(commit=False)
                lesson.created_by = user
                lesson.save()
                class_obj = lesson.class_assigned
                enrolled_students = list(
                    Student.objects.filter(classes=class_obj)
                )
                for stu in enrolled_students:
                    Attendance.objects.get_or_create(
                        lesson=lesson,
                        student=stu,
                        defaults={
                            'status': '',
                            'updated_by': user,
                        }
                    )
            messages.success(request, f'Dərs "{lesson.title_topic}" uğurla yaradıldı!')
            return redirect('core:lesson_attendance', lesson.pk)
    else:
        form = LessonForm(user=user)
    context = build_common_context(request, {'form': form, 'action': 'Əlavə et'})
    return render(request, 'lessons/form.html', context)


@teacher_or_admin_required
def lesson_update(request, pk):
    user = request.user
    if user.is_superuser:
        lesson = get_object_or_404(Lesson.objects.select_related('class_assigned'), pk=pk)
    elif user.is_course_admin:
        managed_teacher_ids = _get_managed_teacher_ids(user)
        lesson_q = _course_admin_lesson_q(user, managed_teacher_ids)
        lesson = get_object_or_404(
            Lesson.objects.filter(lesson_q).distinct().select_related('class_assigned'),
            pk=pk
        )
    else:
        lesson = get_object_or_404(
            Lesson.objects.filter(class_assigned__teacher=user)
            .select_related('class_assigned'),
            pk=pk
        )
    if request.method == 'POST':
        form = LessonForm(request.POST, instance=lesson, user=user)
        if form.is_valid():
            with transaction.atomic():
                lesson = form.save()
                class_obj = lesson.class_assigned
                enrolled_students = list(
                    Student.objects.filter(classes=class_obj)
                )
                for stu in enrolled_students:
                    Attendance.objects.get_or_create(
                        lesson=lesson,
                        student=stu,
                        defaults={
                            'status': '',
                            'updated_by': user,
                        }
                    )
            messages.success(request, f'Dərs "{lesson.title_topic}" uğurla yeniləndi!')
            return redirect('core:lesson_list')
    else:
        form = LessonForm(instance=lesson, user=user)
    context = build_common_context(request, {'form': form, 'action': 'Redaktə et', 'lesson': lesson})
    return render(request, 'lessons/form.html', context)


@teacher_or_admin_required
def lesson_delete(request, pk):
    user = request.user
    if user.is_superuser:
        lesson = get_object_or_404(Lesson.objects.select_related('class_assigned'), pk=pk)
    elif user.is_course_admin:
        lesson_q = _course_admin_lesson_q(user)
        lesson = get_object_or_404(
            Lesson.objects.filter(lesson_q).distinct().select_related('class_assigned'),
            pk=pk
        )
    else:
        lesson = get_object_or_404(
            Lesson.objects.filter(class_assigned__teacher=user)
            .select_related('class_assigned'),
            pk=pk
        )
    if request.method == 'POST':
        topic = lesson.title_topic
        lesson.delete()
        messages.success(request, f'Dərs "{topic}" uğurla silindi!')
        return redirect('core:lesson_list')
    context = build_common_context(request, {'lesson': lesson})
    return render(request, 'lessons/delete.html', context)


@any_authenticated_required
def lesson_detail(request, pk):
    role = get_session_role(request)
    user = request.user
    if role == 'student':
        messages.info(request, 'Şagirdlər dərs ətraflı səhifəsinə daxil ola bilməz. Məlumat dərslər siyahısında göstərilir.')
        return redirect('core:lesson_list')

    if user.is_superuser:
        lesson = get_object_or_404(
            Lesson.objects.select_related('class_assigned', 'class_assigned__teacher'),
            pk=pk
        )
    elif user.is_course_admin:
        lesson_q = _course_admin_lesson_q(user)
        lesson = get_object_or_404(
            Lesson.objects.filter(lesson_q).distinct(
            ).select_related('class_assigned', 'class_assigned__teacher'),
            pk=pk
        )
    else:
        lesson = get_object_or_404(
            Lesson.objects.filter(class_assigned__teacher=user)
            .select_related('class_assigned', 'class_assigned__teacher'),
            pk=pk
        )
    class_obj = lesson.class_assigned
    enrolled_students = list(Student.objects.filter(classes=class_obj))
    student_attendance_map = dict(
        Attendance.objects.filter(lesson=lesson, student__in=enrolled_students)
        .values_list('student_id', 'status')
    )
    attendance_data = [(stu, student_attendance_map.get(stu.pk, '')) for stu in enrolled_students]
    count_ie = sum(1 for _, s in attendance_data if s == 'i/e')
    count_qb = sum(1 for _, s in attendance_data if s == 'q/b')
    count_gecikir = sum(1 for _, s in attendance_data if s == 'gecikir')
    count_icazeli = sum(1 for _, s in attendance_data if s in ('icazeli', 'ü/q'))
    count_grades = sum(1 for _, s in attendance_data if s in [str(i) for i in range(11)])
    count_none = sum(1 for _, s in attendance_data if s == '')

    is_lesson_teacher = (
        user.is_superuser
        or getattr(user, 'is_course_admin', False)
        or lesson.class_assigned.teacher_id == user.pk
    )

    context = build_common_context(request, {
        'lesson': lesson,
        'attendance_data': attendance_data,
        'students': enrolled_students,
        'count_ie': count_ie,
        'count_qb': count_qb,
        'count_gecikir': count_gecikir,
        'count_icazeli': count_icazeli,
        'count_grades': count_grades,
        'count_none': count_none,
        'is_lesson_teacher': is_lesson_teacher,
        'lesson_is_expired': lesson.is_expired,
        'lesson_started_at': lesson.started_at,
        'student_delay_seconds': lesson.student_delay_seconds_remaining,
    })
    return render(request, 'lessons/detail.html', context)


@teacher_or_admin_required
def lesson_attendance(request, pk):
    user = request.user
    if user.is_superuser:
        lesson = get_object_or_404(
            Lesson.objects.select_related('class_assigned', 'class_assigned__teacher'),
            pk=pk
        )
    elif user.is_course_admin:
        managed_teacher_ids = _get_managed_teacher_ids(user)
        lesson_q = _course_admin_lesson_q(user, managed_teacher_ids)
        lesson = get_object_or_404(
            Lesson.objects.filter(lesson_q).distinct(
            ).select_related('class_assigned', 'class_assigned__teacher'),
            pk=pk
        )
    else:
        lesson = get_object_or_404(
            Lesson.objects.filter(class_assigned__teacher=user)
            .select_related('class_assigned', 'class_assigned__teacher'),
            pk=pk
        )
    class_obj = lesson.class_assigned
    enrolled_students = list(Student.objects.filter(classes=class_obj))

    valid_choices = dict(Attendance.STATUS_ALL_CHOICES)

    if request.method == 'POST':
        with transaction.atomic():
            all_atts = list(Attendance.objects.filter(lesson=lesson, student__in=enrolled_students))
            student_att_by_id = {a.student_id: a for a in all_atts if a.student_id}
            atts_to_update = []
            atts_to_create = []

            for stu in enrolled_students:
                status = request.POST.get(f'status_s_{stu.pk}', '')
                if status in valid_choices:
                    attendance = student_att_by_id.get(stu.pk)
                    if attendance is not None:
                        if attendance.status != status:
                            attendance.status = status
                            attendance.updated_by = user
                            atts_to_update.append(attendance)
                    else:
                        atts_to_create.append(Attendance(
                            lesson=lesson,
                            student=stu,
                            status=status,
                            updated_by=user,
                        ))

            if atts_to_create:
                Attendance.objects.bulk_create(atts_to_create)
            if atts_to_update:
                # bulk_update bypasses auto_now, so retain the audit timestamp.
                modified_at = timezone.now()
                for attendance in atts_to_update:
                    attendance.modified_at = modified_at
                fields_to_update = ['status', 'updated_by', 'modified_at']
                Attendance.objects.bulk_update(atts_to_update, fields_to_update)

        messages.success(request, 'Davamiyyət və qiymətləndirmə uğurla yadda saxlanıldı!')
        return redirect('core:lesson_attendance', lesson.pk)

    all_atts = list(Attendance.objects.filter(lesson=lesson, student__in=enrolled_students))
    student_att_map = {a.student_id: a.status for a in all_atts if a.student_id}

    attendance_data = []
    for stu in enrolled_students:
        status = student_att_map.get(stu.pk, '')
        stu._attendance_field_name = f'status_s_{stu.pk}'
        stu._display_name = stu.get_full_name()
        attendance_data.append((stu, status))

    context = build_common_context(request, {
        'lesson': lesson,
        'attendance_data': attendance_data,
        'students': enrolled_students,
        'status_choices': Attendance.STATUS_ALL_CHOICES,
    })
    return render(request, 'lessons/attendance.html', context)


def reklam_list(request):
    query = request.GET.get('q', '')
    ixtisas_filter = request.GET.get('ixtisas', '')
    reklamlar = Reklam.objects.select_related('owner').all()
    if query:
        reklamlar = reklamlar.filter(
            Q(ad__icontains=query) |
            Q(soyad__icontains=query) |
            Q(ixtisas_fenni__icontains=query) |
            Q(owner__first_name__icontains=query) |
            Q(owner__last_name__icontains=query) |
            Q(owner__username__icontains=query) |
            Q(owner__subject__icontains=query)
        )
    if ixtisas_filter:
        reklamlar = reklamlar.filter(
            Q(ixtisas_fenni__icontains=ixtisas_filter) |
            Q(owner__subject__icontains=ixtisas_filter)
        )
    all_ixtisaslar = Reklam.objects.values_list('ixtisas_fenni', flat=True).distinct()

    reklamlar = reklamlar.order_by('-yaradilma_tarixi', '-pk')
    paginator = Paginator(reklamlar, 12)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    role = get_session_role(request)
    user_reklam_count = 0
    can_create = False
    permission_denied_msg = None
    if role in ('teacher', 'admin', 'course_admin'):
        user = request.user
        user_reklam_count = user.get_active_reklam_count()
        if user.is_superuser or user.reklam_icazesi == 'limitsiz':
            can_create = True
        elif user.can_post_reklam:
            if user_reklam_count < 1:
                can_create = True
            else:
                permission_denied_msg = 'İcazə limiti doludur. Yeni reklam yerləşdirmək üçün mövcud reklamı silin.'
        else:
            permission_denied_msg = 'Reklam yerləşdirmək icazəniz yoxdur.'

    context = build_common_context(request, {
        'reklamlar': page_obj,
        'page_obj': page_obj,
        'query': query,
        'ixtisas_filter': ixtisas_filter,
        'all_ixtisaslar': all_ixtisaslar,
        'user_reklam_count': user_reklam_count,
        'can_create': can_create,
        'permission_denied_msg': permission_denied_msg,
        'is_public_page': True,
    })
    return render(request, 'reklamlar/reklam_list.html', context)


def _build_reklam_detail_context(reklam, request, is_owner=False, is_public=False):
    match_source = getattr(reklam.owner, 'subject', None) or reklam.ixtisas_fenni
    match_source = match_source.strip() if match_source else ''
    specialty_matches = []
    specialty_match_ids = set()
    if match_source:
        specialty_matches_qs = Reklam.objects.select_related('owner').filter(
            owner__subject__iexact=match_source
        ).exclude(pk=reklam.pk).order_by('-yaradilma_tarixi')
        specialty_matches = list(specialty_matches_qs)
        if not specialty_matches and reklam.ixtisas_fenni:
            specialty_matches_qs = Reklam.objects.select_related('owner').filter(
                ixtisas_fenni__iexact=reklam.ixtisas_fenni
            ).exclude(pk=reklam.pk).order_by('-yaradilma_tarixi')
            specialty_matches = list(specialty_matches_qs)
    specialty_match_count = len(specialty_matches)
    specialty_match_ids = set(r.pk for r in specialty_matches)
    other_ads_qs = Reklam.objects.select_related('owner').exclude(pk=reklam.pk)
    if specialty_match_ids:
        other_ads_qs = other_ads_qs.exclude(pk__in=specialty_match_ids)
    other_ads = list(other_ads_qs.order_by('-yaradilma_tarixi'))
    MAX_RELATED = 12
    related_ads_blended = specialty_matches + other_ads
    related_ads_list = related_ads_blended[:MAX_RELATED]

    extra = {
        'reklam': reklam,
        'is_owner': is_owner,
        'related_ads': related_ads_list,
        'related_ads_specialty_match': specialty_match_count > 0,
        'related_ads_specialty_count': specialty_match_count,
    }
    if is_public:
        extra['is_public_page'] = True
    return build_common_context(request, extra)


def _get_owned_reklam_or_403(user, pk):
    """Return an advert the user may manage, distinguishing 403 from 404."""
    reklam_qs = Reklam.objects.select_related('owner')
    if user.is_superuser:
        return get_object_or_404(reklam_qs, pk=pk)

    reklam = reklam_qs.filter(pk=pk, owner=user).first()
    if reklam is not None:
        return reklam
    if reklam_qs.filter(pk=pk).exists():
        raise PermissionDenied('Bu reklam üçün icazəniz yoxdur.')
    return get_object_or_404(reklam_qs, pk=pk)


@teacher_or_admin_required
def reklam_detail(request, pk):
    user = request.user
    reklam = _get_owned_reklam_or_403(user, pk)
    context = _build_reklam_detail_context(reklam, request, is_owner=True, is_public=False)
    return render(request, 'reklamlar/reklam_detail.html', context)


def reklam_detail_public(request, pk):
    reklam = get_object_or_404(Reklam.objects.select_related('owner'), pk=pk)
    is_owner = False
    role = get_session_role(request)
    user = request.user
    if role in ('teacher', 'admin', 'course_admin'):
        is_owner = user == reklam.owner
    context = _build_reklam_detail_context(reklam, request, is_owner=is_owner, is_public=True)
    return render(request, 'reklamlar/reklam_detail.html', context)


@teacher_or_admin_required
def reklam_create(request):
    if not request.user.is_superuser and not request.user.can_post_reklam:
        messages.error(request, 'Reklam yerləşdirmək icazəniz yoxdur.')
        return redirect('core:reklam_list')
    user_reklam_count = request.user.get_active_reklam_count()
    if (
        not request.user.is_superuser
        and request.user.reklam_icazesi == 'default'
        and user_reklam_count >= 1
    ):
        messages.warning(request, 'İcazə limiti doludur. Yeni reklam yerləşdirmək üçün mövcud reklamı silin.')
        return redirect('core:reklam_list')
    if request.method == 'POST':
        form = ReklamForm(request.POST, request.FILES)
        if form.is_valid():
            reklam = form.save(commit=False)
            reklam.owner = request.user
            reklam.save()
            messages.success(request, f'Reklam "{reklam.ad} {reklam.soyad}" uğurla yaradıldı!')
            return redirect('core:reklam_detail_admin', reklam.pk)
    else:
        form = ReklamForm()
    context = build_common_context(request, {'form': form, 'action': 'Reklam yarat'})
    return render(request, 'reklamlar/reklam_form.html', context)


@teacher_or_admin_required
def reklam_update(request, pk):
    user = request.user
    reklam = _get_owned_reklam_or_403(user, pk)
    if request.method == 'POST':
        form = ReklamForm(request.POST, request.FILES, instance=reklam)
        if form.is_valid():
            reklam = form.save()
            messages.success(request, f'Reklam "{reklam.ad} {reklam.soyad}" uğurla yeniləndi!')
            return redirect('core:reklam_detail_admin', reklam.pk)
    else:
        form = ReklamForm(instance=reklam)
    context = build_common_context(request, {'form': form, 'action': 'Redaktə et', 'reklam': reklam})
    return render(request, 'reklamlar/reklam_form.html', context)


@teacher_or_admin_required
def reklam_delete(request, pk):
    user = request.user
    reklam = _get_owned_reklam_or_403(user, pk)
    if request.method == 'POST':
        full_name = f'{reklam.ad} {reklam.soyad}'
        reklam.delete()
        messages.success(request, f'Reklam "{full_name}" uğurla silindi!')
        return redirect('core:reklam_list')
    context = build_common_context(request, {'reklam': reklam})
    return render(request, 'reklamlar/reklam_confirm_delete.html', context)


def teacher_application_submit(request):
    if request.method != 'POST':
        return redirect('core:landing_page')

    form = TeacherApplicationForm(request.POST)
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or (request.content_type and 'application/json' in request.content_type)
        or request.POST.get('ajax') == '1'
    )
    if not _allow_public_submission(request, 'teacher_application'):
        error_msg = 'Həddindən artıq müraciət göndərildi. Zəhmət olmasa sonra yenidən cəhd edin.'
        if is_ajax:
            return JsonResponse({'success': False, 'message': error_msg}, status=429)
        messages.error(request, error_msg)
        return redirect('core:landing_page')

    if form.is_valid():
        data = {
            'ad': form.cleaned_data.get('ad', ''),
            'soyad': form.cleaned_data.get('soyad', ''),
            'username': form.cleaned_data.get('username', ''),
            'fenn': form.cleaned_data.get('fenn', ''),
            'email': form.cleaned_data.get('email', ''),
        }

        def _dispatch_teacher_notifications_bg(async_data):
            from django.db import connections
            try:
                notify_teacher_application(async_data)
                print("====== [SUCCESS] Teacher Application notification thread completed successfully ======")
            except Exception as exc:
                print("====== [CRITICAL ERROR] TEACHER APPLICATION NOTIFICATION FAILED ======", flush=True)
                print(f"Error Message: {str(exc)}", flush=True)
                traceback.print_exc()
                print("==========================================================", flush=True)
            finally:
                connections.close_all()

        threading.Thread(
            target=_dispatch_teacher_notifications_bg,
            args=(data,),
            daemon=True
        ).start()

        success_msg = (
            'Məlumatlarınız qeydə alındı. '
            'Az bir müddət sonra hesab məlumatlarınız e-poçt ünvanınıza göndəriləcək.'
        )
        if is_ajax:
            return JsonResponse({'status': 'success', 'success': True, 'message': success_msg})
        messages.success(request, success_msg)
        return redirect('core:landing_page')
    else:
        errors = {}
        for field, field_errors in form.errors.items():
            errors[field] = [str(e) for e in field_errors]

        # FORCE JSON response for all modal template interactions to prevent 4s freeze
        if is_ajax or request.method == 'POST':
            return JsonResponse({
                'success': False,
                'status': 'error',
                'message': 'Form məlumatlarında xəta var. Zəhmət olmasa xanaları düzgün doldurun.',
                'errors': errors,
            }, status=400)

        for field, field_errors in form.errors.items():
            for err in field_errors:
                label = getattr(form.fields.get(field, field), 'label', field)
                messages.error(request, f'{label}: {err}')
        return redirect('core:landing_page')


def feedback_submit(request):
    if request.method != 'POST':
        return redirect('core:landing_page')

    form = FeedbackForm(request.POST)
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or (request.content_type and 'application/json' in request.content_type)
        or request.POST.get('ajax') == '1'
    )
    if not _allow_public_submission(request, 'feedback'):
        error_msg = 'Həddindən artıq rəy göndərildi. Zəhmət olmasa sonra yenidən cəhd edin.'
        if is_ajax:
            return JsonResponse({'success': False, 'message': error_msg}, status=429)
        messages.error(request, error_msg)
        return redirect('core:landing_page')

    if form.is_valid():
        user = getattr(request, 'user', None)
        try:
            feedback = form.save(commit=False)
            if user and user.is_authenticated:
                feedback.created_by = user
            feedback.save()
        except Exception:
            logger.exception('Rəy qeydi verilənlər bazasında saxlanıla bilmədi.')
            error_msg = 'Rəyiniz qeydə alına bilmədi. Zəhmət olmasa yenidən cəhd edin.'
            if is_ajax:
                return JsonResponse({'status': 'error', 'success': False, 'message': error_msg}, status=500)
            messages.error(request, error_msg)
            return redirect('core:landing_page')

        message_text = feedback.message or ''
        if user and user.is_authenticated:
            sender_label = str(getattr(user, 'username', 'Anonim istifadəçi'))
        else:
            sender_label = 'Anonim istifadəçi'

        async_sender = str(sender_label)
        async_message = str(message_text)

        def _dispatch_feedback_notifications_bg(sender, message):
            from django.db import connections
            try:
                notify_feedback(sender, message)
                print("====== [SUCCESS] Feedback notification thread completed successfully ======")
            except Exception as exc:
                print("====== [CRITICAL ERROR] FEEDBACK NOTIFICATION FAILED ======", flush=True)
                print(f"Error Message: {str(exc)}", flush=True)
                traceback.print_exc()
                print("==========================================================", flush=True)
            finally:
                connections.close_all()

        threading.Thread(
            target=_dispatch_feedback_notifications_bg,
            args=(async_sender, async_message),
            daemon=True
        ).start()

        success_msg = 'Rəy və təklifiniz üçün təşəkkür edirik! Məlumatlar qeydə alındı.'
        if is_ajax:
            return JsonResponse({'status': 'success', 'success': True, 'message': success_msg})
        messages.success(request, success_msg)
        return redirect('core:landing_page')
    else:
        errors = {}
        for field, field_errors in form.errors.items():
            errors[field] = [str(e) for e in field_errors]

        # FORCE JSON response for all modal template interactions to prevent 4s freeze
        if is_ajax or request.method == 'POST':
            return JsonResponse({
                'success': False,
                'status': 'error',
                'message': 'Form məlumatlarında xəta var. Zəhmət olmasa xanaları düzgün doldurun.',
                'errors': errors,
            }, status=400)

        for field, field_errors in form.errors.items():
            for err in field_errors:
                label = getattr(form.fields.get(field, field), 'label', field)
                messages.error(request, f'{label}: {err}')
        return redirect('core:landing_page')


@teacher_or_admin_required
def lesson_activate(request, pk):
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or (request.content_type and 'application/json' in request.content_type)
        or request.POST.get('ajax') == '1'
    )

    user = request.user
    if user.is_superuser:
        lesson = get_object_or_404(
            Lesson.objects.select_related('class_assigned', 'class_assigned__teacher'),
            pk=pk
        )
    elif getattr(user, 'is_course_admin', False):
        lesson_q = _course_admin_lesson_q(user)
        lesson = get_object_or_404(
            Lesson.objects.filter(lesson_q).distinct(
            ).select_related('class_assigned', 'class_assigned__teacher'),
            pk=pk
        )
    else:
        lesson = get_object_or_404(
            Lesson.objects.filter(class_assigned__teacher=user)
            .select_related('class_assigned', 'class_assigned__teacher'),
            pk=pk
        )

    if request.method == 'POST':
        try:
            if lesson.is_expired:
                error_msg = 'Dərsin vaxtı artıq bitib. Aktivləşdirmək mümkün deyil.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                    })
                messages.error(request, error_msg)
                return redirect('core:lesson_detail', lesson.pk)

            teacher = getattr(getattr(lesson, 'class_assigned', None), 'teacher', None)
            if teacher and not lesson.lesson_link and getattr(teacher, 'lesson_link', None):
                lesson.lesson_link = teacher.lesson_link
                update_fields = ['is_active', 'started_at', 'lesson_link']
            else:
                update_fields = ['is_active', 'started_at']

            if teacher and not lesson.lesson_link and not getattr(teacher, 'lesson_link', None):
                error_msg = 'Dərs linki təyin olunmayıb. Zəhmət olmasa profilinizdə dərs linkini əlavə edin.'
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'message': error_msg,
                        'edit_profile_url': reverse('core:teacher_update', args=[teacher.pk]),
                    })
                messages.error(request, error_msg)
                return redirect('core:teacher_update', teacher.pk)

            lesson.is_active = True
            if not lesson.started_at:
                lesson.started_at = timezone.now()
            lesson.save(update_fields=update_fields)
            success_msg = 'Dərs aktivləşdirildi. Canlı sessiya başlayır...'
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': success_msg,
                    'lesson_link': lesson.lesson_link or '',
                    'is_active': lesson.is_active,
                    'started_at': lesson.started_at.isoformat() if lesson.started_at else '',
                })
            messages.success(request, success_msg)
            if lesson.lesson_link:
                return redirect(lesson.lesson_link)
            return redirect('core:lesson_detail', lesson.pk)
        except Exception as e:
            logger.exception('lesson_activate POST failed for pk=%s', pk)
            error_msg = 'Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                })
            messages.error(request, error_msg)
            return redirect('core:lesson_detail', lesson.pk)

    if is_ajax:
        return JsonResponse({
            'success': True,
            'is_active': lesson.is_active,
            'lesson_link': lesson.lesson_link or '',
            'started_at': lesson.started_at.isoformat() if lesson.started_at else '',
        })
    return redirect('core:lesson_detail', lesson.pk)


@teacher_or_admin_required
def lesson_deactivate(request, pk):
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or (request.content_type and 'application/json' in request.content_type)
        or request.POST.get('ajax') == '1'
    )

    user = request.user
    if user.is_superuser:
        lesson = get_object_or_404(
            Lesson.objects.select_related('class_assigned', 'class_assigned__teacher'),
            pk=pk
        )
    elif getattr(user, 'is_course_admin', False):
        lesson_q = _course_admin_lesson_q(user)
        lesson = get_object_or_404(
            Lesson.objects.filter(lesson_q).distinct(
            ).select_related('class_assigned', 'class_assigned__teacher'),
            pk=pk
        )
    else:
        lesson = get_object_or_404(
            Lesson.objects.filter(class_assigned__teacher=user)
            .select_related('class_assigned', 'class_assigned__teacher'),
            pk=pk
        )

    if request.method == 'POST':
        try:
            lesson.is_active = False
            lesson.save(update_fields=['is_active'])
            success_msg = 'Dərs dayandırıldı. Şagirdlər üçün giriş bağlandı.'
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': success_msg,
                    'is_active': lesson.is_active,
                })
            messages.success(request, success_msg)
            return redirect('core:lesson_detail', lesson.pk)
        except Exception as e:
            logger.exception('lesson_deactivate POST failed for pk=%s', pk)
            error_msg = 'Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.'
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': error_msg,
                })
            messages.error(request, error_msg)
            return redirect('core:lesson_detail', lesson.pk)

    if is_ajax:
        return JsonResponse({
            'success': True,
            'is_active': lesson.is_active,
        })
    return redirect('core:lesson_detail', lesson.pk)
