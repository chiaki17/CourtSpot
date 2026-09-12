"""Court availability checker via bookingMap API (Optimized)."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

URL = os.environ.get("COURT_URL", "https://court.ozzy.asia/court-demo")
TZ = ZoneInfo("Asia/Bangkok")
STATE_FILE = os.environ.get("STATE_FILE", "state/notified.json")

# ช่วงเวลาที่สนใจ (Tuple เพื่อ immutable & lookup เร็ว)
WEEKDAY_TARGETS = (18, 19)              # 19:00-20:00 และ 20:00-21:00
WEEKEND_TARGETS = (15, 16, 17, 18, 19)  # 16:00-17:00 ถึง 20:00-21:00

# ใช้ requests.Session() ร่วมกันเพื่อ reuse connection pool (ลดเวลา handshake)
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; CourtChecker/1.0)",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://court.ozzy.asia",
    "Referer": URL,
})


@dataclass(frozen=True, slots=True)
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


def _resolve_date(day_num: int, today: date) -> date | None:
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
        if d >= today:
            return d
    return None


def fetch_booking_map() -> dict[str, Any]:
    # ลด timeout เป็น (connect=3.05, read=10) และใช้ session เดียวกัน
    attempts = [
        ("POST json {}", lambda: _SESSION.post(URL, json={}, timeout=(3.05, 10))),
        ("POST empty",   lambda: _SESSION.post(URL, data=b"", timeout=(3.05, 10))),
        ("GET",          lambda: _SESSION.get(URL, timeout=(3.05, 10))),
    ]

    last_err: Exception | None = None
    for name, fn in attempts:
        try:
            r = fn()
            r.raise_for_status()
            # ใช้ r.content แทน r.text เพื่อหลีกเลี่ยง overhead ของ chardet
            data = json.loads(r.content)
            if isinstance(data, dict) and "bookingMap" in data:
                logger.info("API OK via %s — days=%s", name, list(data["bookingMap"].keys()))
                return data["bookingMap"]
        except Exception as e:
            last_err = e
            logger.warning("[%s] failed: %s", name, e)

    raise RuntimeError(f"Cannot fetch bookingMap from {URL}") from last_err


def parse_available_slots(booking_map: dict[str, Any]) -> list[Slot]:
    today = _today_bkk()
    available: list[Slot] = []

    for day_str, courts in booking_map.items():
        try:
            day_num = int(day_str)
        except ValueError:
            continue

        d = _resolve_date(day_num, today)
        if d is None or not isinstance(courts, dict):
            continue

        # เลือกเฉพาะชั่วโมงเป้าหมาย และแปลงวันที่ครั้งเดียว
        target_hours = WEEKEND_TARGETS if d.weekday() >= 5 else WEEKDAY_TARGETS
        date_str = d.isoformat()

        for court_str, hours in courts.items():
            if not isinstance(hours, dict):
                continue
            court_name = str(court_str)

            # Direct lookup เฉพาะ target hours ไม่ต้องสร้าง set หรือวนลูป 16 ชั่วโมง
            for hour in target_hours:
                val = hours.get(str(hour))
                if val is True or val == "true" or val == "True":
                    continue
                available.append(Slot(court=court_name, date=date_str, hour=hour))

    available.sort(key=lambda s: (s.date, s.hour, s.court))
    return available


def fetch_availability() -> list[Slot]:
    booking_map = fetch_booking_map()
    slots = parse_available_slots(booking_map)
    # รวบ Log ให้เหลือครั้งเดียว ลด stdout I/O overhead
    if slots:
        logger.info("Matching available slots (%d):\n%s", len(slots), "\n".join(f"  FREE {s.display}" for s in slots))
    else:
        logger.info("Matching available slots: 0")
    return slots


def load_notified() -> set[str]:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_notified(keys: set[str]) -> None:
    os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    today_str = _today_bkk().isoformat()
    keys = {k for k in keys if k.split("|", 1)[0] >= today_str}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        # compact json ไม่ต้องเคาะ space
        json.dump(sorted(keys), f, ensure_ascii=False, separators=(",", ":"))