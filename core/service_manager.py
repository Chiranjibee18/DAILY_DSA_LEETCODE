"""
Systemd Service Manager for Linux (User Session).
Automates daemon installation, enablement, starting, stopping, and status reporting.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SERVICE_NAME = "git-auto-push.service"
USER_SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
SERVICE_DEST = USER_SYSTEMD_DIR / SERVICE_NAME

SERVICE_TEMPLATE = """[Unit]
Description=Git Auto Push Heatmap Engine (IST Daily Slots & Catch-Up)
After=network-online.target default.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={repo_dir}
ExecStart={python_bin} {repo_dir}/auto_push.py run-daemon
Restart=always
RestartSec=15
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""

def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

def install_service() -> tuple[bool, str]:
    """Generates the service file, reloads systemd user daemon, and enables + starts the service."""
    USER_SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
    python_bin = sys.executable

    content = SERVICE_TEMPLATE.format(
        repo_dir=str(BASE_DIR),
        python_bin=python_bin
    )

    with open(SERVICE_DEST, "w", encoding="utf-8") as f:
        f.write(content)

    # Reload systemd
    code, _, err = run_cmd(["systemctl", "--user", "daemon-reload"])
    if code != 0:
        return False, f"systemctl --user daemon-reload failed: {err}"

    # Enable and start
    code, _, err = run_cmd(["systemctl", "--user", "enable", "--now", SERVICE_NAME])
    if code != 0:
        return False, f"Failed to enable and start service: {err}"

    return True, f"Service '{SERVICE_NAME}' installed and started successfully."

def uninstall_service() -> tuple[bool, str]:
    """Stops, disables, and removes the systemd service."""
    run_cmd(["systemctl", "--user", "stop", SERVICE_NAME])
    run_cmd(["systemctl", "--user", "disable", SERVICE_NAME])

    if SERVICE_DEST.exists():
        SERVICE_DEST.unlink()

    run_cmd(["systemctl", "--user", "daemon-reload"])
    return True, f"Service '{SERVICE_NAME}' uninstalled."

def get_service_status() -> dict:
    """Returns is_active, is_enabled, and unit details."""
    installed = SERVICE_DEST.exists()
    if not installed:
        return {
            "installed": False,
            "active": False,
            "enabled": False,
            "details": "Not installed"
        }

    _, active_out, _ = run_cmd(["systemctl", "--user", "is-active", SERVICE_NAME])
    _, enabled_out, _ = run_cmd(["systemctl", "--user", "is-enabled", SERVICE_NAME])
    _, status_out, _ = run_cmd(["systemctl", "--user", "status", SERVICE_NAME])

    return {
        "installed": True,
        "active": active_out == "active",
        "enabled": enabled_out == "enabled",
        "details": status_out
    }
