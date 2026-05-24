import os
import smtplib
import markdown
from email.message import EmailMessage
from dotenv import load_dotenv


load_dotenv()

EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()
EMAIL_TO = os.getenv("EMAIL_TO", "").strip()
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()


def markdown_to_html(markdown_text: str) -> str:
    converted = markdown.markdown(
        markdown_text,
        extensions=["extra", "nl2br"]
    )

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{
      font-family: Arial, sans-serif;
      line-height: 1.5;
      color: #222;
      background-color: #f7f7f7;
      padding: 24px;
    }}

    .container {{
      max-width: 850px;
      margin: 0 auto;
      background: white;
      padding: 28px;
      border-radius: 12px;
      border: 1px solid #ddd;
    }}

    h1 {{
      font-size: 26px;
      color: #111;
    }}

    h2 {{
      font-size: 20px;
      margin-top: 28px;
      border-bottom: 1px solid #ddd;
      padding-bottom: 6px;
    }}

    a {{
      color: #0a66c2;
      text-decoration: none;
    }}

    hr {{
      border: none;
      border-top: 1px solid #ddd;
      margin: 24px 0;
    }}
  </style>
</head>
<body>
  <div class="container">
    {converted}
  </div>
</body>
</html>
"""

def send_email(subject, body):
    if not EMAIL_FROM or not EMAIL_TO or not GMAIL_APP_PASSWORD:
        return {
            "status": "failed",
            "error": "Missing EMAIL_FROM, EMAIL_TO, or GMAIL_APP_PASSWORD"
        }

    html_body = markdown_to_html(body)

    message = EmailMessage()
    message["From"] = EMAIL_FROM
    message["To"] = EMAIL_TO
    message["Subject"] = subject

    # Plain text fallback
    message.set_content(body)

    # HTML version
    message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_FROM, GMAIL_APP_PASSWORD)
            smtp.send_message(message)

        return {
            "status": "sent",
            "to": EMAIL_TO,
            "subject": subject,
        }

    except smtplib.SMTPAuthenticationError as error:
        return {
            "status": "failed",
            "error_type": "SMTPAuthenticationError",
            "message": "Gmail rejected EMAIL_FROM or GMAIL_APP_PASSWORD.",
            "details": str(error),
        }

    except Exception as error:
        return {
            "status": "failed",
            "error_type": type(error).__name__,
            "message": str(error),
        }