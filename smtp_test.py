import os
from dotenv import load_dotenv
from email.message import EmailMessage
import smtplib

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
ALERT_TO = os.getenv("ALERT_TO", "")
ALERT_FROM = os.getenv("ALERT_FROM", SMTP_USER)

if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_TO, ALERT_FROM]):
    raise SystemExit("Missing SMTP config in .env")

msg = EmailMessage()
msg["Subject"] = "MLS Bot SMTP test"
msg["From"] = ALERT_FROM
msg["To"] = ALERT_TO
msg.set_content("If you got this, SMTP works.")

print("Sending test email...")
with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
    s.ehlo()
    s.starttls()
    s.ehlo()
    s.login(SMTP_USER, SMTP_PASS)
    s.send_message(msg)

print("Sent ✅")
