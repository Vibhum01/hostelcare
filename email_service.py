
import os
import smtplib

from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

GMAIL_ADDRESS = os.getenv('GMAIL_ADDRESS')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')


def send_email(receiver, subject, body):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        return False

    message = EmailMessage()
    message['From'] = GMAIL_ADDRESS
    message['To'] = receiver
    message['Subject'] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=20) as server:
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(message)

        return True

    except Exception:
        return False
