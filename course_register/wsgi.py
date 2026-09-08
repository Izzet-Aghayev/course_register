import os
import sys
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'course_register.settings')

# Vercel hər dəfə başlayanda həm miqrasiyaları edəcək, həm də hazır məlumatları bazaya vuracaq
try:
    from django.core.management import call_command
    # 1. Cədvəlləri tam sıfırdan qurur
    call_command('migrate', interactive=False)
    # 2. Sizin yazdığınız hazır məlumatları və admin hesabını bazaya yükləyir
    call_command('seed_data', interactive=False)
    print("Verilənlər bazası strukturu və hazır məlumatlar uğurla quraşdırıldı!")
except Exception as e:
    print(f"Avtomatik verilənlər bazası tənzimləmə xətası: {e}", file=sys.stderr)

application = get_wsgi_application()
app = application
