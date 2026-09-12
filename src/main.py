"""Entry: fetch → diff state → email → save."""
from __future__ import annotations

import logging
import sys
from dotenv import load_dotenv

load_dotenv()

from .checker import fetch_availability, load_notified, save_notified
from .notifier import send_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("main")


def main() -> int:
    try:
        slots = fetch_availability()
    except Exception:
        log.exception("Fetch failed")
        return 1

    seen = load_notified()
    new_slots = [s for s in slots if s.key not in seen]

    if not new_slots:
        log.info("No new slots (tracked=%d, currently_free=%d)", len(seen), len(slots))
        return 0

    log.info("New slots to notify: %d", len(new_slots))
    try:
        send_email(new_slots)
        seen.update(s.key for s in new_slots)
        save_notified(seen)
    except Exception:
        log.exception("Notify failed")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())