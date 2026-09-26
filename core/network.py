"""
Network connectivity checker for git-auto-push.
Verifies internet and GitHub reachability reliably with low latency.
"""

import socket
import logging

logger = logging.getLogger("git-auto-push.network")

CHECK_TARGETS = [
    ("github.com", 22, "GitHub SSH"),
    ("github.com", 443, "GitHub HTTPS"),
    ("1.1.1.1", 53, "Cloudflare DNS"),
    ("8.8.8.8", 53, "Google DNS")
]

def is_online(timeout: float = 3.0) -> bool:
    """
    Check if the system is currently connected to the internet and can reach GitHub.
    Tries each target sequentially until one succeeds.
    """
    for host, port, desc in CHECK_TARGETS:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                logger.debug("Successfully connected to %s (%s:%d)", desc, host, port)
                return True
        except (socket.timeout, OSError) as e:
            logger.debug("Failed connecting to %s (%s:%d): %s", desc, host, port, e)
            continue
    return False

def check_status(timeout: float = 3.0) -> dict:
    """
    Return detailed network status for diagnostics.
    """
    results = {}
    online = False
    for host, port, desc in CHECK_TARGETS:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                results[desc] = "OK"
                online = True
        except Exception as e:
            results[desc] = f"FAILED: {e}"

    return {
        "online": online,
        "targets": results
    }
