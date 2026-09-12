"""Email notifier (Gmail App Password / any SMTP)."""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Sequence

from .checker import Slot

logger = logging.getLogger(__name__)


def send_email(slots: Sequence[Slot]) -> None:
    if not slots:
        return

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    to_addr = os.environ["EMAIL_TO"]
    court_url = os.environ.get("COURT_URL", "https://court.ozzy.asia/court-demo")

    msg = EmailMessage()
    msg["Subject"] = f"🎾 พบคอร์ทว่าง {len(slots)} slot!"
    msg["From"] = user
    msg["To"] = to_addr

    lines = ["สนามเทนนิสว่างในช่วงเวลาที่ตั้งไว้:\n"]
    for s in slots:
        lines.append(f"  • {s.display}")
    lines += ["", f"จองได้ที่: {court_url}", "", "(แจ้งอัตโนมัติจาก tennis-court-checker)"]
    msg.set_content("\n".join(lines))

    html_items = "".join(f"<li><b>{s.display}</b></li>" for s in slots)
    html = f"""\
    <h2>🎾 คอร์ทว่าง {len(slots)} slot</h2>
    <ul>{html_items}</ul>
    <p><a href="{court_url}">🔗 ไปจองเลย</a></p>
    <p style="color:#888;font-size:12px">auto-notify · tennis-court-checker</p>
    """
    msg.add_alternative(html, subtype="html")

    logger.info("Sending email (%d slots) → %s", len(slots), to_addr)
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)
    logger.info("Email sent OK")