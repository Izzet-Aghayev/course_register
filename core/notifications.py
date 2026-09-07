import logging
from typing import Dict, Any

try:
    from decouple import config
except ImportError:
    import os

    def config(key, default=None, cast=None):
        val = os.environ.get(key, default)
        if cast and val is not None:
            try:
                val = cast(val)
            except (ValueError, TypeError):
                pass
        return val

from django.conf import settings
from django.core.mail import get_connection, send_mail
import requests

logger = logging.getLogger(__name__)


TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


def _send_email_safely(subject: str, body: str, from_email: str, recipient_list) -> bool:
    """Send mail with the project-level SMTP connection timeout applied."""
    try:
        connection = get_connection(timeout=settings.EMAIL_TIMEOUT)
        return bool(send_mail(
            subject,
            body,
            from_email,
            recipient_list,
            fail_silently=False,
            connection=connection,
        ))
    except Exception as exc:
        logger.error('E-poçt bildirişi göndərilərkən xəta: %s', exc)
        return False


def _send_telegram_message(url: str, payload: Dict[str, Any]) -> bool:
    """Synchronously send one Telegram request with a reasonable timeout."""
    try:
        response = requests.post(url, json=payload, timeout=5.0)
        if response.status_code == 200:
            return True
        logger.error('Telegram cavab kodu: %s, body: %s', response.status_code, response.text)
    except Exception as exc:
        logger.warning('Telegram bildirişi göndərilə bilmədi: %s', exc)
    return False


def _get_config() -> Dict[str, Any]:
    notification_receiver_email = ''
    try:
        from django.conf import settings as _s
        notification_receiver_email = getattr(_s, 'NOTIFICATION_RECEIVER_EMAIL', '')
    except Exception:
        pass

    if not notification_receiver_email:
        notification_receiver_email = config('NOTIFICATION_RECEIVER_EMAIL', '')

    email_host_user = ''
    try:
        from django.conf import settings as _s
        email_host_user = getattr(_s, 'EMAIL_HOST_USER', '')
    except Exception:
        pass
    if not email_host_user:
        email_host_user = config('EMAIL_HOST_USER', '')

    default_from_email = ''
    try:
        from django.conf import settings as _s
        default_from_email = getattr(_s, 'DEFAULT_FROM_EMAIL', '')
    except Exception:
        pass
    if not default_from_email:
        default_from_email = config('DEFAULT_FROM_EMAIL', email_host_user or '')

    telegram_bot_token = ''
    try:
        from django.conf import settings as _s
        telegram_bot_token = getattr(_s, 'TELEGRAM_BOT_TOKEN', '')
    except Exception:
        pass
    if not telegram_bot_token:
        telegram_bot_token = config('TELEGRAM_BOT_TOKEN', '')

    telegram_chat_id = ''
    try:
        from django.conf import settings as _s
        telegram_chat_id = getattr(_s, 'TELEGRAM_CHAT_ID', '')
    except Exception:
        pass
    if not telegram_chat_id:
        telegram_chat_id = config('TELEGRAM_CHAT_ID', '')

    return {
        'email_host_user': email_host_user,
        'default_from_email': default_from_email or email_host_user,
        'notification_receiver_email': notification_receiver_email,
        'telegram_bot_token': telegram_bot_token,
        'telegram_chat_id': telegram_chat_id,
    }


def _build_message_text(data: Dict[str, Any]) -> str:
    ad = data.get('ad', '') or '-'
    soyad = data.get('soyad', '') or '-'
    username = data.get('username', '') or '-'
    fenn = data.get('fenn', '') or '-'
    email = data.get('email', '') or '-'

    lines = [
        '=== Yeni Müəllim Müraciəti ===',
        f'Ad: {ad}',
        f'Soyad: {soyad}',
        f'İstifadəçi adı (Tələb olunan): {username}',
        f'Fənn: {fenn}',
        f'E-poçt: {email}',
        '==============================',
    ]
    return '\n'.join(lines)


def send_teacher_application_email(application_data: Dict[str, Any]) -> bool:
    cfg = _get_config()
    if not (cfg['email_host_user'] and cfg['notification_receiver_email']):
        logger.warning(
            'SMTP/EMAIL ayarları tamamlanmadığı üçün e-poçt bildirişi göndərilmədi. '
            'EMAIL_HOST_USER və NOTIFICATION_RECEIVER_EMAIL yoxlanılmalıdır.'
        )
        return False

    ad = application_data.get('ad', '')
    soyad = application_data.get('soyad', '')
    name_part = ' '.join(p for p in [ad, soyad] if p).strip() or 'Müəllim'
    subject = f'Yeni Müəllim Müraciəti - {name_part}'

    message_text = _build_message_text(application_data)
    from_email = cfg['default_from_email'] or cfg['email_host_user']
    recipient_list = [cfg['notification_receiver_email']]

    if _send_email_safely(subject, message_text, from_email, recipient_list):
        logger.info(
            'Müəllim müraciəti e-poçtu göndərildi: %s -> %s',
            application_data.get('email'),
            cfg['notification_receiver_email'],
        )
        return True
    return False


def send_teacher_application_telegram(application_data: Dict[str, Any]) -> bool:
    cfg = _get_config()
    token = cfg['telegram_bot_token']
    chat_id = cfg['telegram_chat_id']
    if not (token and chat_id):
        logger.warning(
            'Telegram bot token və ya chat id təyin edilmədiyi üçün bildiriş göndərilmədi. '
            'TELEGRAM_BOT_TOKEN və TELEGRAM_CHAT_ID yoxlanılmalıdır.'
        )
        return False

    text = _build_message_text(application_data)
    url = TELEGRAM_API_BASE.format(token=token, method='sendMessage')
    payload = {
        'chat_id': chat_id,
        'text': text,
    }

    if _send_telegram_message(url, payload):
        logger.info(
            'Müəllim müraciəti Telegram-a göndərildi: %s %s',
            application_data.get('ad'),
            application_data.get('soyad'),
        )
        return True
    return False


def notify_teacher_application(application_data: Dict[str, Any]) -> Dict[str, bool]:
    results = {
        'email': False,
        'telegram': False,
    }
    try:
        results['email'] = send_teacher_application_email(application_data)
    except Exception as exc:
        logger.error('notify_teacher_application e-poçt çağırışı xətası: %s', exc)
    try:
        results['telegram'] = send_teacher_application_telegram(application_data)
    except Exception as exc:
        logger.error('notify_teacher_application telegram çağırışı xətası: %s', exc)
    if not any(results.values()):
        logger.warning(
            'Heç bir bildiriş kanalı aktiv deyil. Müraciət: %s %s / %s',
            application_data.get('ad'),
            application_data.get('soyad'),
            application_data.get('email'),
        )
    return results


def _build_limit_exceeded_message(username: str) -> str:
    return f'İstifadəçi {username} müəllim yaratmaq limitinə çatdı. Limit artırılması tələb olunur.'


def send_limit_exceeded_email(username: str) -> bool:
    cfg = _get_config()
    if not (cfg['email_host_user'] and cfg['notification_receiver_email']):
        logger.warning(
            'SMTP/EMAIL ayarları tamamlanmadığı üçün limit aşımı bildirişi göndərilmədi.'
        )
        return False

    subject = f'Müəllim Limiti Aşıldı - {username}'
    message_text = _build_limit_exceeded_message(username)
    from_email = cfg['default_from_email'] or cfg['email_host_user']
    recipient_list = [cfg['notification_receiver_email']]

    if _send_email_safely(subject, message_text, from_email, recipient_list):
        logger.info('Müəllim limiti aşımı e-poçtu göndərildi: %s', username)
        return True
    return False


def send_limit_exceeded_telegram(username: str) -> bool:
    cfg = _get_config()
    token = cfg['telegram_bot_token']
    chat_id = cfg['telegram_chat_id']
    if not (token and chat_id):
        logger.warning(
            'Telegram bot token və ya chat id təyin edilmədiyi üçün limit aşımı bildirişi göndərilmədi.'
        )
        return False

    text = _build_limit_exceeded_message(username)
    url = TELEGRAM_API_BASE.format(token=token, method='sendMessage')
    payload = {
        'chat_id': chat_id,
        'text': text,
    }

    if _send_telegram_message(url, payload):
        logger.info('Müəllim limiti aşımı Telegram-a göndərildi: %s', username)
        return True
    return False


def notify_teacher_limit_exceeded(username) -> Dict[str, bool]:
    if hasattr(username, 'username'):
        username_str = str(username.username)
    else:
        username_str = str(username)

    results = {
        'email': False,
        'telegram': False,
    }
    try:
        results['email'] = send_limit_exceeded_email(username_str)
    except Exception as exc:
        logger.error('notify_teacher_limit_exceeded e-poçt çağırışı xətası: %s', exc)
    try:
        results['telegram'] = send_limit_exceeded_telegram(username_str)
    except Exception as exc:
        logger.error('notify_teacher_limit_exceeded telegram çağırışı xətası: %s', exc)
    if not any(results.values()):
        logger.warning(
            'Heç bir bildiriş kanalı aktiv deyil. Limit aşımı bildirişi: %s',
            username_str,
        )
    return results


def _build_feedback_message(sender_label: str, message_text: str) -> str:
    lines = [
        '=== Yeni Rəy / Şikayət ===',
        f'Göndərən: {sender_label}',
        f'Mesaj: {message_text}',
        '=========================',
    ]
    return '\n'.join(lines)


def send_feedback_email(sender_label: str, message_text: str) -> bool:
    cfg = _get_config()
    if not (cfg['email_host_user'] and cfg['notification_receiver_email']):
        logger.warning(
            'SMTP/EMAIL ayarları tamamlanmadığı üçün rəy bildirişi göndərilmədi. '
            'EMAIL_HOST_USER və NOTIFICATION_RECEIVER_EMAIL yoxlanılmalıdır.'
        )
        return False

    subject = f'Yeni Rəy / Şikayət - {sender_label}'
    body = _build_feedback_message(sender_label, message_text)
    from_email = cfg['default_from_email'] or cfg['email_host_user']
    recipient_list = [cfg['notification_receiver_email']]

    if _send_email_safely(subject, body, from_email, recipient_list):
        logger.info(
            'Rəy bildirişi e-poçtu göndərildi: göndərən=%s -> %s',
            sender_label,
            cfg['notification_receiver_email'],
        )
        return True
    return False


def send_feedback_telegram(sender_label: str, message_text: str) -> bool:
    cfg = _get_config()
    token = cfg['telegram_bot_token']
    chat_id = cfg['telegram_chat_id']
    if not (token and chat_id):
        logger.warning(
            'Telegram bot token və ya chat id təyin edilmədiyi üçün rəy bildirişi göndərilmədi. '
            'TELEGRAM_BOT_TOKEN və TELEGRAM_CHAT_ID yoxlanılmalıdır.'
        )
        return False

    text = _build_feedback_message(sender_label, message_text)
    url = TELEGRAM_API_BASE.format(token=token, method='sendMessage')
    payload = {
        'chat_id': chat_id,
        'text': text,
    }

    if _send_telegram_message(url, payload):
        logger.info(
            'Rəy bildirişi Telegram-a göndərildi: göndərən=%s',
            sender_label,
        )
        return True
    return False


def notify_feedback(sender_label: str, message_text: str) -> Dict[str, bool]:
    results = {
        'email': False,
        'telegram': False,
    }
    try:
        results['email'] = send_feedback_email(sender_label, message_text)
    except Exception as exc:
        logger.error('notify_feedback e-poçt çağırışı xətası: %s', exc)
    try:
        results['telegram'] = send_feedback_telegram(sender_label, message_text)
    except Exception as exc:
        logger.error('notify_feedback telegram çağırışı xətası: %s', exc)
    if not any(results.values()):
        logger.warning(
            'Heç bir bildiriş kanalı aktiv deyil. Rəy bildirişi: göndərən=%s',
            sender_label,
        )
    return results

