import os
from pathlib import Path

try:
    from decouple import config
except ImportError:
    import os as _os

    def config(key, default=None, cast=None):
        val = _os.environ.get(key, default)
        if cast and val is not None:
            try:
                val = cast(val)
            except (ValueError, TypeError):
                pass
        return val

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('DJANGO_SECRET_KEY', 'django-insecure-course-register-secret-key-change-in-production-2024')

DEBUG = config('DEBUG', True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', '*').split(',') if config('ALLOWED_HOSTS', '*') != '*' else ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'crispy_forms',
    'crispy_bootstrap5',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Mütləq bu sətirdə olmalıdır!
    'django.contrib.sessions.middleware.SessionMiddleware',
    # ... digər middleware kodlarınız ...
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.AccountLifetimeMiddleware',
]

ROOT_URLCONF = 'course_register.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.carousel_reklamlar',
                'core.context_processors.session_role_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'course_register.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME', 'course_register_db'),
        'USER': config('DB_USER', 'root'),
        'PASSWORD': config('DB_PASSWORD', '12345678'),
        'HOST': config('DB_HOST', '127.0.0.1'),
        'PORT': config('DB_PORT', '3306'),
        'OPTIONS': {
            'ssl': {'ssl_mode': 'REQUIRED'}
        }
    }
}

# A filesystem-backed cache is shared by all workers on this deployment, unlike
# Django's default per-process local-memory cache.  It protects login counters
# and notification de-duplication consistently when multiple workers run.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'az'

TIME_ZONE = 'Asia/Baku'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'core.User'

LOGIN_URL = 'core:login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'core:login'

from django.contrib.messages import constants as message_constants

MESSAGE_TAGS = {
    message_constants.DEBUG: 'secondary',
    message_constants.INFO: 'info',
    message_constants.SUCCESS: 'success',
    message_constants.WARNING: 'warning',
    message_constants.ERROR: 'danger',
}

CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

EMAIL_BACKEND = config('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', '')
EMAIL_PORT = config('EMAIL_PORT', 587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', '').strip('"').strip("'")
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER if EMAIL_HOST_USER else '')
SERVER_EMAIL = config('SERVER_EMAIL', DEFAULT_FROM_EMAIL)
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', 10, cast=int)

NOTIFICATION_RECEIVER_EMAIL = config('NOTIFICATION_RECEIVER_EMAIL', '')
TELEGRAM_BOT_TOKEN = config('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = config('TELEGRAM_CHAT_ID', '')
SITE_NAME = config('SITE_NAME', 'TəlimQeyd')
