"""
Scheduler engine for git-auto-push.
Handles IST timezone calculations, slot tracking, 3-4 hour retry buffers,
and zero-miss daily catch-up logic.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from core import content_manager, git_manager, network

logger = logging.getLogger("git-auto-push.scheduler")
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "remote_url": "git@github.com:Chiranjibee18/git-auto-push.git",
    "branch": "main",
    "timezone": "Asia/Kolkata",
    "schedule_slots": [
        {"id": "07:00", "name": "Morning Slot", "time": "07:00"},
        {"id": "10:00", "name": "Mid-Morning Slot", "time": "10:00"},
        {"id": "12:00", "name": "Noon Slot", "time": "12:00"},
        {"id": "16:00", "name": "Afternoon Slot", "time": "16:00"}
    ],
    "retry_buffer_hours": 4,
    "check_interval_seconds": 60,
    "ensure_daily_commit": True
}

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception as e:
            logger.warning("Could not read config.json, using defaults: %s", e)
    return DEFAULT_CONFIG

def get_tz(config: dict) -> ZoneInfo:
    tz_str = config.get("timezone", "Asia/Kolkata")
    try:
        return ZoneInfo(tz_str)
    except Exception:
        return ZoneInfo("Asia/Kolkata")

def get_now(config: dict) -> datetime:
    return datetime.now(get_tz(config))

def determine_catchup_slot(now: datetime, slots: list) -> tuple[str, str]:
    """Find the most fitting slot id and name for an immediate catch-up commit."""
    current_time_str = now.strftime("%H:%M")
    
    # Check which slot matches or is the most recently passed
    passed_slots = [s for s in slots if s["time"] <= current_time_str]
    if passed_slots:
        latest = passed_slots[-1]
        return latest["id"], latest["name"]
    # If earlier than 07:00 AM, assign to the first slot
    return slots[0]["id"], slots[0]["name"]

def evaluate_schedule(config: dict, state: dict) -> tuple[bool, str, str, str]:
    """
    Evaluates whether a commit should happen right now.
    Returns: (should_commit, slot_id, slot_name, reason)
    """
    now = get_now(config)
    today_str = now.strftime("%Y-%m-%d")
    buffer_hours = config.get("retry_buffer_hours", 4)
    ensure_daily = config.get("ensure_daily_commit", True)
    slots = config.get("schedule_slots", DEFAULT_CONFIG["schedule_slots"])

    today_record = state.get("dates", {}).get(today_str, {"completed_slots": [], "count": 0})
    completed = today_record.get("completed_slots", [])
    count = today_record.get("count", 0)

    # 1. Zero-miss day guarantee:
    # If today has NO commits yet, trigger immediately on boot/connect!
    if ensure_daily and count == 0:
        slot_id, slot_name = determine_catchup_slot(now, slots)
        return True, slot_id, f"Daily Catch-up ({slot_name})", "Securing today's green contribution square (0 commits today)"

    # 2. Check each slot against its buffer window
    tz = get_tz(config)
    for slot in slots:
        slot_id = slot["id"]
        slot_name = slot["name"]
        
        if slot_id in completed:
            continue

        # Parse slot time for today
        try:
            h, m = map(int, slot["time"].split(":"))
            slot_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        except Exception:
            continue

        window_start = slot_dt
        window_end = slot_dt + timedelta(hours=buffer_hours)

        # If we are within the slot's active window (or within buffer retry)
        if window_start <= now <= window_end:
            return True, slot_id, slot_name, f"Slot {slot['time']} is active (window: {window_start.strftime('%H:%M')} - {window_end.strftime('%H:%M')})"

    return False, "", "", "No slots currently due"

def get_next_slot_summary(config: dict, state: dict) -> dict:
    """Returns status of today's slots and the next upcoming slot."""
    now = get_now(config)
    today_str = now.strftime("%Y-%m-%d")
    slots = config.get("schedule_slots", DEFAULT_CONFIG["schedule_slots"])
    today_record = state.get("dates", {}).get(today_str, {"completed_slots": [], "count": 0})
    completed = today_record.get("completed_slots", [])

    next_slot = None
    for slot in slots:
        try:
            h, m = map(int, slot["time"].split(":"))
            slot_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if slot_dt > now and slot["id"] not in completed:
                next_slot = {
                    "id": slot["id"],
                    "name": slot["name"],
                    "time": slot["time"],
                    "time_until": str(slot_dt - now).split(".")[0]
                }
                break
        except Exception:
            pass

    return {
        "today": today_str,
        "current_time_ist": now.strftime("%Y-%m-%d %H:%M:%S IST"),
        "commits_today": today_record.get("count", 0),
        "completed_slots": completed,
        "next_slot": next_slot
    }

def run_cycle(force: bool = False, force_slot_id: str = None) -> dict:
    """
    Executes a single check cycle.
    1. Checks network connectivity.
    2. Checks if commit should occur.
    3. If so, updates content, creates commit, and pushes to remote.
    """
    config = load_config()
    state = content_manager.load_state()
    now = get_now(config)

    online = network.is_online()
    if not online:
        logger.info("Internet is currently offline. Skipping push; will retry in buffer window.")
        return {
            "status": "offline",
            "message": "Internet connection not detected. Will retry when connected.",
            "online": False
        }

    should_run = force
    slot_id = force_slot_id or "Manual"
    slot_name = "Manual Trigger"
    reason = "Forced run"

    if not force:
        should_run, slot_id, slot_name, reason = evaluate_schedule(config, state)

    if not should_run:
        logger.debug("Evaluation result: %s", reason)
        return {
            "status": "idle",
            "message": reason,
            "online": True
        }

    logger.info("Executing commit for slot %s (%s). Reason: %s", slot_name, slot_id, reason)

    # 1. Update state & README
    commit_msg, quote_text = content_manager.record_commit(slot_id, slot_name, now)

    # 2. Stage and commit
    commit_ok, commit_detail = git_manager.stage_and_commit(commit_msg)
    if not commit_ok:
        logger.error("Commit failed: %s", commit_detail)
        return {
            "status": "commit_failed",
            "message": commit_detail,
            "online": True
        }

    # 3. Push to GitHub
    branch = config.get("branch", "main")
    push_ok, push_detail = git_manager.sync_and_push("origin", branch)

    return {
        "status": "success" if push_ok else "push_warning",
        "slot": slot_name,
        "slot_id": slot_id,
        "commit_message": commit_msg,
        "quote": quote_text,
        "push_result": push_detail,
        "push_ok": push_ok,
        "online": True
    }
