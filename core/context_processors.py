from django.db.utils import OperationalError, ProgrammingError
from django.contrib import admin as django_admin

from .models import Reklam, Student


def carousel_reklamlar(request):
    reklamlar = []
    slides = []
    try:
        reklamlar = list(
            Reklam.objects.select_related('owner').order_by('-yenilenme_tarixi')[:12]
        )
        chunk_size = 3
        slides = [
            reklamlar[i:i + chunk_size]
            for i in range(0, len(reklamlar), chunk_size)
        ]
    except (OperationalError, ProgrammingError):
        reklamlar = []
        slides = []
    return {
        'carousel_reklamlar': reklamlar,
        'carousel_reklam_slides': slides,
    }


def session_role_context(request):
    ctx = {
        'is_teacher': False,
        'is_student': False,
        'is_admin': False,
        'is_course_admin': False,
        'session_role': None,
        'current_user_display': '',
        'current_student': None,
        'can_create_teachers': False,
        'teacher_creation_limit': 0,
        'lesson_link': '',
    }
    try:
        student_id = request.session.get('student_id') if hasattr(request, 'session') else None
        user = getattr(request, 'user', None)
        if student_id is not None:
            try:
                student = Student.objects.get(pk=student_id)
                ctx['is_student'] = True
                ctx['session_role'] = 'student'
                ctx['current_student'] = student
                ctx['current_user_display'] = student.get_full_name()
            except Student.DoesNotExist:
                pass
        elif user is not None and user.is_authenticated:
            if user.is_superuser:
                ctx['is_admin'] = True
                ctx['is_teacher'] = True
                ctx['is_course_admin'] = True
                ctx['session_role'] = 'admin'
                ctx['can_create_teachers'] = True
            elif getattr(user, 'is_course_admin', False):
                ctx['is_course_admin'] = True
                ctx['is_teacher'] = True
                ctx['session_role'] = 'course_admin'
                ctx['can_create_teachers'] = (
                    getattr(user, 'teacher_creation_limit', 0) > 0
                )
            elif getattr(user, 'is_teacher', False):
                ctx['is_teacher'] = True
                ctx['session_role'] = 'teacher'
            ctx['teacher_creation_limit'] = getattr(user, 'teacher_creation_limit', 0)
            ctx['lesson_link'] = getattr(user, 'lesson_link', '') or ''
            ctx['current_user_display'] = user.get_full_name() or user.username
    except Exception:
        pass
    return ctx
