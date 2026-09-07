from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import logout
from django.urls import resolve, Resolver404
from django.utils import timezone
from .models import Student


ACCOUNT_EXPIRED_MESSAGE = (
    'Hesabınızın istifadə müddəti bitmişdir. '
    'Xahiş edirik sistem inzibatçısı ilə əlaqə saxlayın.'
)


PUBLIC_PATHS = {
    'core:login',
    'core:student_login',
    'core:landing_page',
    'core:reklam_list',
    'core:reklam_detail',
    'core:teacher_application_submit',
    'admin:index',
}


def _is_public_path(request):
    try:
        match = resolve(request.path_info)
        if match and match.url_name:
            namespace = match.namespace or ''
            full_name = f'{namespace}:{match.url_name}' if namespace else match.url_name
            if full_name in PUBLIC_PATHS:
                return True
            if match.url_name in {'login', 'student_login', 'landing_page'}:
                return True
    except Resolver404:
        pass
    if request.path_info in ('/', '/login/', '/student/login/'):
        return True
    return False


class AccountLifetimeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if _is_public_path(request):
            return None

        student_id = request.session.get('student_id')
        if student_id:
            if Student.objects.filter(pk=student_id, activity_status=True).exists():
                return None
            request.session.pop('student_id', None)
            messages.error(request, ACCOUNT_EXPIRED_MESSAGE)
            return redirect('core:student_login')

        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return None

        if user.is_superuser:
            return None

        if user.deactivation_date and timezone.now() > user.deactivation_date:
            if user.is_active:
                user.is_active = False
                user.save(update_fields=['is_active'])
            logout(request)
            messages.error(request, ACCOUNT_EXPIRED_MESSAGE)
            return redirect('core:login')

        return None
