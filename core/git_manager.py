"""
Git operations manager for git-auto-push.
Handles staging, committing, pulling, rebasing, and pushing with comprehensive error reporting.
"""

import subprocess
import logging
from pathlib import Path

logger = logging.getLogger("git-auto-push.git")
BASE_DIR = Path(__file__).resolve().parent.parent

def run_git(args: list[str], cwd: Path = BASE_DIR) -> tuple[int, str, str]:
    """Execute a git command within repository directory."""
    cmd = ["git"] + args
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

def init_repo_if_needed():
    """Ensure the repo is initialized with branch main."""
    if not (BASE_DIR / ".git").exists():
        run_git(["init", "-b", "main"])
    else:
        # Ensure branch is main
        code, branch, _ = run_git(["branch", "--show-current"])
        if branch != "main":
            run_git(["branch", "-M", "main"])

def get_remote_url(remote_name: str = "origin") -> str:
    """Get the URL of the specified remote, or empty string if not configured."""
    code, out, _ = run_git(["remote", "get-url", remote_name])
    return out if code == 0 else ""

def set_remote_url(url: str, remote_name: str = "origin") -> bool:
    """Set or update remote URL."""
    existing = get_remote_url(remote_name)
    if existing:
        code, _, err = run_git(["remote", "set-url", remote_name, url])
    else:
        code, _, err = run_git(["remote", "add", remote_name, url])
    return code == 0

def stage_and_commit(message: str) -> tuple[bool, str]:
    """
    Stages changed tracking files and creates a commit.
    """
    init_repo_if_needed()
    
    files_to_stage = ["README.md", "data/state.json", "data/activity.log", "config.json"]
    existing_files = [f for f in files_to_stage if (BASE_DIR / f).exists()]
    
    if not existing_files:
        return False, "No files found to stage."

    code, _, err = run_git(["add"] + existing_files)
    if code != 0:
        return False, f"git add failed: {err}"

    # Check if there are staged changes
    code, status_out, _ = run_git(["diff", "--cached", "--name-only"])
    if not status_out:
        return True, "No changes to commit (working tree clean)."

    code, out, err = run_git(["commit", "-m", message])
    if code != 0:
        return False, f"git commit failed: {err}"
    
    return True, out

def sync_and_push(remote_name: str = "origin", branch: str = "main") -> tuple[bool, str]:
    """
    Pull with rebase from remote if branch exists, then push to remote.
    """
    remote_url = get_remote_url(remote_name)
    if not remote_url:
        return False, f"Remote '{remote_name}' is not configured. Use `python3 auto_push.py set-remote <url>` to configure it."

    # Try pull --rebase (it's okay if remote is empty or branch doesn't exist yet)
    run_git(["pull", "--rebase", remote_name, branch])

    # Push to remote
    code, out, err = run_git(["push", "-u", remote_name, branch])
    if code == 0:
        return True, "Push successful."
    else:
        error_msg = err or out
        return False, f"Push failed: {error_msg}"
