"""SSH helper — runs commands and transfers files over SSH.

Relies on the user's ~/.ssh/config (ControlMaster, etc.) for auth.
"""

from __future__ import annotations

import logging
import subprocess

logger = logging.getLogger("openmodal.cluster.ssh")


def run(host: str, command: str, *, timeout: int | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command on a remote host via SSH."""
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        logger.error(f"SSH command failed on {host}: {command}\nstderr: {result.stderr}")
        raise RuntimeError(f"SSH command failed on {host}: {result.stderr.strip()}")
    return result


def run_background(host: str, command: str, *, log_file: str) -> str:
    """Run a command on a remote host in the background via nohup.

    Uses 'bash -c' to ensure the nohup + redirect + & works properly
    over SSH, and returns the PID of the background process.
    """
    # Escape single quotes in the command for bash -c '...'
    escaped = command.replace("'", "'\\''")
    bg_cmd = f"nohup bash -c '{escaped}' > {log_file} 2>&1 & echo $!"
    result = run(host, bg_cmd)
    pid = result.stdout.strip().split("\n")[-1]
    logger.debug(f"Started background process on {host}: PID {pid}")
    return pid


def rsync(local_path: str, host: str, remote_path: str) -> None:
    """rsync a local file/directory to a remote host."""
    subprocess.run(
        ["rsync", "-az", "--delete", local_path, f"{host}:{remote_path}"],
        check=True, capture_output=True,
    )


def scp_to(local_path: str, host: str, remote_path: str) -> None:
    """Copy a local file to a remote host."""
    subprocess.run(
        ["scp", "-q", local_path, f"{host}:{remote_path}"],
        check=True, capture_output=True,
    )


def scp_from(host: str, remote_path: str, local_path: str) -> None:
    """Copy a file from a remote host to local."""
    subprocess.run(
        ["scp", "-q", f"{host}:{remote_path}", local_path],
        check=True, capture_output=True,
    )


def is_reachable(host: str) -> bool:
    """Check if we can SSH to the host (e.g., control socket is active)."""
    result = subprocess.run(
        ["ssh", "-O", "check", host],
        capture_output=True, text=True,
    )
    return result.returncode == 0
