"""Court availability checker via bookingMap API."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

URL = os.environ.get("COURT_URL", "https://court.ozzy.asia/court-demo")
TZ = ZoneInfo("Asia/Bangkok")

# ช่วงที่สนใจ (ชั่วโมงเริ่มต้นของ slot)
WEEKDAY_HOURS = [18, 19]               # → slot 19:00-20:00 และ 20:00-21:00
WEEKEND_HOURS = list(range(15, 20))    # → slot 16:00-17:00 ถึง 20:00-21:00

def is_target_hour(d: date, hour: int) -> bool:
    if d.weekday() >= 5:  # Sat=5, Sun=6
        return hour in WEEKEND_HOURS
    return hour in WEEKDAY_HOURS

# ชั่วโมงที่สนามเปิด (จากข้อมูลจริง)
OPEN_HOURS = list(range(6, 22))  # 6..21

STATE_FILE = os.environ.get("STATE_FILE", "state/notified.json")


@dataclass(frozen=True)
class Slot:
    court: str
    date: str   # YYYY-MM-DD
    hour: int

    @property
    def key(self) -> str:
        return f"{self.date}|{self.court}|{self.hour:02d}"

    @property
    def display(self) -> str:
        return f"{self.date} {self.hour+1:02d}:00-{self.hour+2:02d}:00 @ {self.court}"


def _today_bkk() -> date:
    return datetime.now(TZ).date()


def is_target_hour(d: date, hour: int) -> bool:
    if d.weekday() >= 5:  # Sat=5 Sun=6
        return hour in WEEKEND_HOURS
    return hour in WEEKDAY_HOURS


def _resolve_date(day_num: int, today: date) -> date | None:
    """
    แปลงเลขวัน (1-31) → date จริง
    ลองเดือนปัจจุบันก่อน ถ้าวันนั้นผ่านไปแล้ว ลองเดือนถัดไป
    """
    for month_offset in (0, 1):
        m = today.month + month_offset
        y = today.year
        if m > 12:
            m -= 12
            y += 1
        try:
            d = date(y, m, day_num)
        except ValueError:
            continue
        # ยอมรับวันนี้และอนาคต (ไม่เอาอดีต)
        if d >= today:
            return d
    return None


def fetch_booking_map() -> dict[str, Any]:
    """
    เรียก API — ลองหลายแบบของ POST body
    (เว็บเป็น SPA ยิง POST กลับมาที่ path เดียวกัน)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CourtChecker/1.0)",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://court.ozzy.asia",
        "Referer": URL,
    }

    # ลองทีละแบบ จนได้ bookingMap
    attempts = [
        ("POST json {}", lambda: requests.post(URL, json={}, headers=headers, timeout=30)),
        ("POST empty", lambda: requests.post(URL, data=b"", headers=headers, timeout=30)),
        ("POST no body", lambda: requests.post(URL, headers={k: v for k, v in headers.items() if k != "Content-Type"}, timeout=30)),
        ("GET", lambda: requests.get(URL, headers=headers, timeout=30)),
    ]

    last_err: Exception | None = None
    for name, fn in attempts:
        try:
            r = fn()
            r.raise_for_status()
            # บางที response เป็น HTML ปน — พยายาม parse JSON
            try:
                data = r.json()
            except Exception:
                # ถ้าเป็น text ที่มี JSON ฝัง
                text = r.text.strip()
                if text.startswith("{"):
                    data = json.loads(text)
                else:
                    logger.warning("[%s] non-JSON status=%s len=%d", name, r.status_code, len(r.text))
                    continue
            if isinstance(data, dict) and "bookingMap" in data:
                logger.info("API OK via %s — days=%s", name, list(data["bookingMap"].keys()))
                return data["bookingMap"]
            logger.warning("[%s] JSON but no bookingMap keys=%s", name, list(data)[:10] if isinstance(data, dict) else type(data))
        except Exception as e:
            last_err = e
            logger.warning("[%s] failed: %s", name, e)

    raise RuntimeError(f"Cannot fetch bookingMap from {URL}") from last_err


def parse_available_slots(booking_map: dict[str, Any]) -> list[Slot]:
    """
    bookingMap[day][court][hour] = true  → จองแล้ว
    ชั่วโมงที่ไม่มี key หรือเป็น false     → ว่าง
    """
    today = _today_bkk()
    available: list[Slot] = []

    for day_str, courts in booking_map.items():
        try:
            day_num = int(day_str)
        except ValueError:
            continue
        d = _resolve_date(day_num, today)
        if d is None:
            continue

        if not isinstance(courts, dict):
            continue

        for court_str, hours in courts.items():
            if not isinstance(hours, dict):
                continue
            # ชั่วโมงที่จองแล้ว
            booked = {int(h) for h, v in hours.items() if str(v).lower() == "true" or v is True}
            # ชั่วโมงที่อาจ false ชัดเจน
            explicitly_free = {int(h) for h, v in hours.items() if v is False or str(v).lower() == "false"}

            for hour in OPEN_HOURS:
                is_free = hour in explicitly_free or hour not in booked
                # ถ้า hour อยู่ใน map เป็น true → ไม่ free
                if hour in booked:
                    is_free = False
                if not is_free:
                    continue
                if not is_target_hour(d, hour):
                    continue
                available.append(Slot(court=str(court_str), date=d.isoformat(), hour=hour))

    available.sort(key=lambda s: (s.date, s.hour, s.court))
    return available


def fetch_availability() -> list[Slot]:
    booking_map = fetch_booking_map()
    slots = parse_available_slots(booking_map)
    logger.info("Matching available slots: %d", len(slots))
    for s in slots:
        logger.info("  FREE %s", s.display)
    return slots


# ---------- state กันแจ้งซ้ำ ----------
def load_notified() -> set[str]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_notified(keys: set[str]) -> None:
    os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    today_str = _today_bkk().isoformat()
    # เก็บเฉพาะอนาคต
    keys = {k for k in keys if k.split("|")[0] >= today_str}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(keys), f, indent=2, ensure_ascii=False)