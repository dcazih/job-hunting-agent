import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv


load_dotenv()

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


def send_email(subject, body):
    if not EMAIL_FROM or not EMAIL_TO or not GMAIL_APP_PASSWORD:
        raise RuntimeError("Missing EMAIL_FROM, EMAIL_TO, or GMAIL_APP_PASSWORD in .env")

    message = EmailMessage()
    message["From"] = EMAIL_FROM
    message["To"] = EMAIL_TO
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
        smtp.send_message(message)

    return {
        "status": "sent",
        "to": EMAIL_TO,
        "subject": subject,
    }