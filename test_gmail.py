import os
import smtplib
from email.message import EmailMessage


def _load_local_env():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    env_path = os.path.join(base_dir, ".env")
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as e:
        print(f".env load warning: {e}")


_load_local_env()


def _normalize_phone(phone):
    phone = (phone or "").strip().replace(" ", "")
    if not phone:
        return ""
    if phone.startswith("+"):
        return phone
    return f"+{phone}"


def _send_email_alert(recipient_email, message_text, subject="Intruder Alert"):
    sender_email = os.getenv("ALERT_SENDER_EMAIL", "").strip()
    app_password = os.getenv("ALERT_GMAIL_APP_PASSWORD", "").strip().replace(" ", "")
    smtp_server = os.getenv("ALERT_SMTP_SERVER", "smtp.gmail.com").strip()
    try:
        smtp_port = int(os.getenv("ALERT_SMTP_PORT", "465").strip() or "465")
        smtp_timeout = float(os.getenv("ALERT_SMTP_TIMEOUT", "20").strip() or "20")
    except ValueError:
        return False, "Invalid SMTP port/timeout in environment"
    smtp_use_tls = os.getenv("ALERT_SMTP_USE_TLS", "").strip().lower() in ("1", "true", "yes")

    if not sender_email or not app_password or not recipient_email:
        return False, "Missing email configuration"

    msg = EmailMessage()
    msg.set_content(message_text)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = recipient_email

    try:
        # Port 465 -> implicit SSL, port 587 (or explicit flag) -> STARTTLS.
        if smtp_port == 465 and not smtp_use_tls:
            with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=smtp_timeout) as smtp:
                smtp.login(sender_email, app_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=smtp_timeout) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(sender_email, app_password)
                smtp.send_message(msg)
        return True, "Email sent"
    except Exception as e:
        return False, f"Email failed: {e}"


def _send_sms_alert(recipient_phone, message_text):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    twilio_number = os.getenv("TWILIO_PHONE_NUMBER", "").strip()
    recipient_phone = _normalize_phone(recipient_phone)

    if not account_sid or not auth_token or not twilio_number or not recipient_phone:
        return False, "Missing SMS configuration"

    try:
        from twilio.rest import Client
    except Exception:
        return False, "Twilio SDK not installed"

    try:
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=message_text,
            from_=twilio_number,
            to=recipient_phone,
        )
        return True, f"SMS sent ({message.sid})"
    except Exception as e:
        return False, f"SMS failed: {e}"


def send_dual_alert(user_email, user_phone, message_text, subject="Intruder Alert"):
    email_ok, email_status = _send_email_alert(user_email, message_text, subject=subject)
    sms_ok, sms_status = _send_sms_alert(user_phone, message_text)
    return {
        "email_target": (user_email or "").strip(),
        "sms_target": _normalize_phone(user_phone),
        "email_ok": email_ok,
        "email_status": email_status,
        "sms_ok": sms_ok,
        "sms_status": sms_status,
    }

