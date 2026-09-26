#!/usr/bin/env python3
"""
Git Auto Push - Automated GitHub Heatmap Engine
Schedules daily commits (07:00, 10:00, 12:00, 16:00 IST),
includes 3-4 hr offline retry buffers, and guarantees zero-miss day catch-up on laptop boot.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure root directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from core import content_manager, git_manager, network, scheduler, service_manager

LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "git-auto-push.log"

def setup_logging(verbose: bool = False):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Avoid duplicate handlers
    root_logger.handlers = [file_handler, stream_handler]

def cmd_daemon(args):
    """Run the persistent daemon loop."""
    setup_logging(args.verbose)
    logger = logging.getLogger("git-auto-push.daemon")
    config = scheduler.load_config()
    interval = config.get("check_interval_seconds", 60)

    logger.info("=" * 60)
    logger.info("Starting Git Auto Push Daemon (IST Schedule Engine)")
    logger.info("Target slots: 07:00, 10:00, 12:00, 16:00 IST (Buffer: %d hrs)", config.get("retry_buffer_hours", 4))
    logger.info("Check interval: %d seconds | Timezone: %s", interval, config.get("timezone", "Asia/Kolkata"))
    logger.info("=" * 60)

    # Initial check on boot / restart
    try:
        res = scheduler.run_cycle(force=False)
        logger.info("Startup check result: %s", res.get("message") or res.get("status"))
    except Exception as e:
        logger.error("Error during startup cycle: %s", e)

    while True:
        try:
            time.sleep(interval)
            res = scheduler.run_cycle(force=False)
            if res.get("status") in ["success", "commit_failed", "push_warning"]:
                logger.info("Cycle completed: %s -> %s", res.get("slot"), res.get("message") or res.get("push_result"))
        except KeyboardInterrupt:
            logger.info("Daemon received interrupt signal. Shutting down gracefully.")
            break
        except Exception as e:
            logger.error("Unexpected error in daemon loop: %s", e, exc_info=True)
            time.sleep(10)

def cmd_run_once(args):
    """Run a single check or force an immediate commit/push."""
    setup_logging(args.verbose)
    logger = logging.getLogger("git-auto-push.run_once")
    
    print("Checking status and executing cycle...")
    result = scheduler.run_cycle(force=args.force, force_slot_id=args.slot)
    
    status = result.get("status")
    print(f"\nResult Status: {status.upper()}")
    print(f"Online:        {'YES' if result.get('online') else 'NO'}")
    
    if "slot" in result:
        print(f"Slot:          {result.get('slot')} ({result.get('slot_id')})")
        print(f"Commit Msg:    {result.get('commit_message')}")
        print(f"Thought:       {result.get('quote')}")
        print(f"Push Result:   {result.get('push_result')}")
    else:
        print(f"Detail:        {result.get('message')}")

def cmd_status(args):
    """Display rich status dashboard in terminal."""
    config = scheduler.load_config()
    state = content_manager.load_state()
    summary = scheduler.get_next_slot_summary(config, state)
    net_status = network.check_status()
    svc_status = service_manager.get_service_status()
    remote_url = git_manager.get_remote_url("origin") or "(not configured)"

    print("=" * 65)
    print("         🟢 GIT AUTO PUSH - HEATMAP ENGINE STATUS")
    print("=" * 65)
    print(f"  Current Time (IST) : {summary['current_time_ist']}")
    print(f"  Internet Online    : {'✅ Yes' if net_status['online'] else '❌ No (Offline)'}")
    print(f"  GitHub SSH Reach   : {'✅ Connected' if net_status['targets'].get('GitHub SSH') == 'OK' else '❌ ' + str(net_status['targets'].get('GitHub SSH'))}")
    print(f"  Remote URL         : {remote_url}")
    print(f"  Current Streak     : 🔥 {state.get('current_streak', 0)} Day(s)")
    print(f"  Total Pushes       : 📦 {state.get('total_commits', 0)}")
    print("-" * 65)
    print("  📅 Today's Slots Status (07:00, 10:00, 12:00, 16:00 IST):")
    completed = set(summary["completed_slots"])
    slots = config.get("schedule_slots", [])
    for s in slots:
        status_sym = "🟢 COMPLETED" if s["id"] in completed else "⏳ PENDING"
        print(f"    • {s['time']} IST ({s['name']:<18}) : {status_sym}")

    print(f"  Today's Commits    : {summary['commits_today']}")
    if summary.get("next_slot"):
        ns = summary["next_slot"]
        print(f"  Next Slot          : ⏭️  {ns['time']} IST ({ns['name']}) [in {ns['time_until']}]")
    else:
        print(f"  Next Slot          : ✅ All slots finished for today!")

    print("-" * 65)
    print("  ⚙️  System Service (systemd user daemon):")
    print(f"    • Installed      : {'Yes' if svc_status['installed'] else 'No'}")
    print(f"    • Active/Running : {'🟢 Active' if svc_status['active'] else '🔴 Inactive'}")
    print(f"    • Enabled on Boot: {'✅ Enabled' if svc_status['enabled'] else '❌ Disabled'}")
    print("=" * 65)

def cmd_set_remote(args):
    """Set or update the remote repository URL."""
    url = args.url.strip()
    if not url:
        print("Error: Remote URL cannot be empty.")
        sys.exit(1)

    ok = git_manager.set_remote_url(url, "origin")
    if ok:
        # Also update config.json
        config = scheduler.load_config()
        config["remote_url"] = url
        with open(scheduler.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        print(f"✅ Remote 'origin' updated to: {url}")
        print(f"   Saved to config.json and git remote.")
    else:
        print(f"❌ Failed to set remote URL: {url}")
        sys.exit(1)

def cmd_install_service(args):
    """Install and enable systemd user service."""
    ok, msg = service_manager.install_service()
    if ok:
        print(f"✅ {msg}")
        print("\nThe daemon is now registered with systemd and will run automatically on system boot/login!")
        print("To check status: python3 auto_push.py status")
        print("To view system logs: journalctl --user -u git-auto-push -f")
    else:
        print(f"❌ Error: {msg}")
        sys.exit(1)

def cmd_uninstall_service(args):
    """Uninstall systemd user service."""
    ok, msg = service_manager.uninstall_service()
    print(f"ℹ️  {msg}")

def cmd_logs(args):
    """Display recent logs."""
    lines_count = args.lines
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-lines_count:]:
                    print(line, end="")
        except Exception as e:
            print(f"Error reading log file: {e}")
    else:
        print("No log file found yet.")

def main():
    parser = argparse.ArgumentParser(
        description="Git Auto Push - Automated GitHub Heatmap Engine (IST Slots & Zero-Miss Catch-Up)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # daemon
    p_daemon = subparsers.add_parser("run-daemon", help="Run the continuous background daemon")
    p_daemon.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging")
    p_daemon.set_defaults(func=cmd_daemon)

    # run-once
    p_once = subparsers.add_parser("run-once", help="Check schedule and run one commit/push cycle")
    p_once.add_argument("--force", "-f", action="store_true", help="Force commit/push immediately regardless of schedule")
    p_once.add_argument("--slot", type=str, default=None, help="Optional slot id (e.g. 07:00, 10:00, 12:00, 16:00)")
    p_once.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging")
    p_once.set_defaults(func=cmd_run_once)

    # status
    p_status = subparsers.add_parser("status", help="Show current status, streak, and slots")
    p_status.set_defaults(func=cmd_status)

    # set-remote
    p_remote = subparsers.add_parser("set-remote", help="Set GitHub remote repository URL")
    p_remote.add_argument("url", type=str, help="Repository URL (e.g. git@github.com:Chiranjibee18/git-auto-push.git)")
    p_remote.set_defaults(func=cmd_set_remote)

    # install-service
    p_inst = subparsers.add_parser("install-service", help="Install & start systemd user service for auto-start on boot")
    p_inst.set_defaults(func=cmd_install_service)

    # uninstall-service
    p_uninst = subparsers.add_parser("uninstall-service", help="Stop & remove systemd user service")
    p_uninst.set_defaults(func=cmd_uninstall_service)

    # logs
    p_logs = subparsers.add_parser("logs", help="View recent logs")
    p_logs.add_argument("-n", "--lines", type=int, default=30, help="Number of lines to show (default: 30)")
    p_logs.set_defaults(func=cmd_logs)

    args = parser.parse_args()
    if not args.command:
        # Default action when run with no arguments is status
        cmd_status(args)
    else:
        args.func(args)

if __name__ == "__main__":
    main()
