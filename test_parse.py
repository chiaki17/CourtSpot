"""ทดสอบ parse กับข้อมูลจริงที่ capture มา"""
import json
from src.checker import parse_available_slots

# วาง body_preview เต็ม ๆ ที่ได้จาก API (หรือยิงสด)
sample = {
  "12": {
    "1": {"10": True, "11": True, "12": True, "13": True, "14": True,
          "15": True, "16": True, "17": True, "18": True, "19": True,
          "20": True, "21": True, "6": True, "7": True, "8": True, "9": True},
    # ... courts อื่น
  },
  "14": {
    "3": {"10": True, "11": True, "12": True, "13": True, "14": True,
          "15": True, "16": True, "17": True, "18": True, "19": True,
          "20": True, "6": True, "8": True, "9": True},  # ไม่มี 7, 21
  }
}

slots = parse_available_slots(sample)
print(f"found {len(slots)} slots")
for s in slots:
    print(" ", s.display)