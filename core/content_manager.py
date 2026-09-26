"""
Content and Activity Manager for git-auto-push.
Maintains state, tracks streaks, updates README.md, and generates meaningful commit messages.
"""

import json
import os
import random
from datetime import datetime, date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"
QUOTES_FILE = DATA_DIR / "quotes.json"
README_FILE = BASE_DIR / "README.md"
ACTIVITY_LOG_FILE = DATA_DIR / "activity.log"

DEFAULT_QUOTES = [
    {"quote": "Consistency is what transforms average into excellence.", "author": "Unknown"},
    {"quote": "Talk is cheap. Show me the code.", "author": "Linus Torvalds"},
    {"quote": "Small daily improvements over time lead to stunning results.", "author": "Robin Sharma"},
    {"quote": "First, solve the problem. Then, write the code.", "author": "John Johnson"},
    {"quote": "Make it work, make it right, make it fast.", "author": "Kent Beck"}
]

def load_quotes() -> list:
    if QUOTES_FILE.exists():
        try:
            with open(QUOTES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_QUOTES

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "total_commits": 0,
        "current_streak": 0,
        "last_active_date": "",
        "dates": {}
    }

def save_state(state: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def calculate_streak(history_dates: dict, today_str: str) -> int:
    """Calculate the consecutive active days streak ending today or yesterday."""
    if not history_dates:
        return 0
    
    current_date = date.fromisoformat(today_str)
    # Check if today has activity
    streak = 0
    if today_str in history_dates and history_dates[today_str].get("count", 0) > 0:
        streak += 1
        check_date = current_date - timedelta(days=1)
    else:
        # Check if yesterday had activity
        yesterday_str = (current_date - timedelta(days=1)).isoformat()
        if yesterday_str in history_dates and history_dates[yesterday_str].get("count", 0) > 0:
            check_date = current_date - timedelta(days=1)
        else:
            return 0
    
    while True:
        day_str = check_date.isoformat()
        if day_str in history_dates and history_dates[day_str].get("count", 0) > 0:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break
            
    return streak

def record_commit(slot_id: str, slot_name: str, now_dt: datetime) -> tuple[str, str]:
    """
    Update state, calculate streak, append activity log, and update README.
    Returns (commit_message, quote_text).
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today_str = now_dt.strftime("%Y-%m-%d")
    time_str = now_dt.strftime("%H:%M:%S")
    ist_timestamp = f"{today_str} {time_str} IST"

    # Select quote
    quotes = load_quotes()
    selected_quote = random.choice(quotes)
    quote_text = f"\"{selected_quote['quote']}\" — {selected_quote['author']}"

    # Load and update state
    state = load_state()
    state["total_commits"] = state.get("total_commits", 0) + 1

    dates = state.setdefault("dates", {})
    day_record = dates.setdefault(today_str, {
        "completed_slots": [],
        "count": 0,
        "last_time": ""
    })
    
    if slot_id not in day_record["completed_slots"]:
        day_record["completed_slots"].append(slot_id)
    day_record["count"] = day_record.get("count", 0) + 1
    day_record["last_time"] = ist_timestamp
    state["last_active_date"] = today_str

    # Recalculate streak
    state["current_streak"] = calculate_streak(dates, today_str)
    save_state(state)

    # Append to activity log
    log_entry = f"[{ist_timestamp}] Slot: {slot_name} ({slot_id}) | Commits today: {day_record['count']} | {quote_text}\n"
    with open(ACTIVITY_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)

    # Format commit message
    commit_msg = f"chore(pulse): {slot_name} [{slot_id} IST] - {today_str} ({selected_quote['author']})"

    # Update README.md
    update_readme(state, today_str, ist_timestamp, slot_name, slot_id, quote_text)

    return commit_msg, quote_text

def update_readme(state: dict, today_str: str, last_updated: str, last_slot_name: str, last_slot_id: str, quote: str):
    """Render a clean, modern README showing streak, status badges, and recent activity log."""
    total = state.get("total_commits", 0)
    streak = state.get("current_streak", 0)
    today_info = state.get("dates", {}).get(today_str, {"completed_slots": [], "count": 0})
    completed_slots = today_info.get("completed_slots", [])
    
    # Slot checkmarks
    slots_display = []
    for s_id, s_name in [("07:00", "07:00 AM IST"), ("10:00", "10:00 AM IST"), ("12:00", "12:00 PM IST"), ("16:00", "04:00 PM IST")]:
        status_icon = "🟢 Completed" if s_id in completed_slots else "⏳ Pending"
        slots_display.append(f"| **{s_name}** | {status_icon} |")

    # Read last 10 entries from activity log
    recent_entries = []
    if ACTIVITY_LOG_FILE.exists():
        try:
            with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                recent_entries = lines[-10:][::-1] # last 10 in reverse chronological
        except Exception:
            pass

    recent_table_rows = []
    for entry in recent_entries:
        # format: [2026-09-26 11:45:00 IST] Slot: Morning Slot (07:00) | Commits today: 1 | "Quote" — Author
        if "]" in entry and "|" in entry:
            parts = entry.split("|")
            ts_slot = parts[0].strip("[] ").split("] Slot: ")
            ts = ts_slot[0].strip("[]")
            slot = ts_slot[1] if len(ts_slot) > 1 else "Scheduled"
            q = parts[-1].strip()
            recent_table_rows.append(f"| `{ts}` | {slot} | {q} |")
        else:
            recent_table_rows.append(f"| Log | {entry} | — |")

    recent_table_md = "\n".join(recent_table_rows) if recent_table_rows else "| — | No activity recorded yet | — |"
    slots_table_md = "\n".join(slots_display)

    readme_content = f"""# 🟢 Git Auto Push Heatmap Engine

[![Streak](https://img.shields.io/badge/Current%20Streak-{streak}%20Days-brightgreen?style=for-the-badge&logo=github)](https://github.com/Chiranjibee18)
[![Total Commits](https://img.shields.io/badge/Total%20Pushed-{total}-blue?style=for-the-badge)](https://github.com/Chiranjibee18)
[![Timezone](https://img.shields.io/badge/Schedule-IST%20(UTC%2B5:30)-orange?style=for-the-badge)](https://github.com/Chiranjibee18)
[![System](https://img.shields.io/badge/Daemon-systemd%20service-success?style=for-the-badge)](https://github.com/Chiranjibee18)

> Automated git activity synchronization system engineered to maintain an active GitHub contribution heatmap every single day without missing.

---

### 📅 Today's Slots Status (`{today_str}`)

| Slot Time | Status |
| :--- | :--- |
{slots_table_md}

* **Commits Recorded Today:** `{today_info.get('count', 0)}`
* **Last Synchronization:** `{last_updated}`
* **Last Slot:** `{last_slot_name} ({last_slot_id})`

---

### 💡 Daily Thought
> {quote}

---

### ⏱️ Target Schedule (Indian Standard Time - IST)
- 🌅 **07:00 AM IST** (Morning Slot)
- ☕ **10:00 AM IST** (Mid-Morning Slot)
- ☀️ **12:00 PM IST** (Noon Slot)
- 🌆 **04:00 PM IST** (Afternoon Slot)
- 🛡️ **Zero-Miss Buffer**: When booting or connecting to internet, automatic catch-up triggers immediately to safeguard every single day's green streak!

---

### 📜 Recent Activity History

| Timestamp (IST) | Slot | Message / Thought |
| :--- | :--- | :--- |
{recent_table_md}

---
*Maintained automatically by `git-auto-push` engine.*
"""
    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(readme_content)
