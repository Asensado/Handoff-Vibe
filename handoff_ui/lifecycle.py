# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Asensado
"""Handoff-owned process lifecycle, independent of the Bluetooth adapter."""
import fcntl
import os
import signal
import subprocess


def acquire_lease(folder, name):
    # Never unlink a lock: an old process can still own the original inode.
    fd = os.open(folder / name, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    return os.fdopen(fd, 'w')


def stop_backend(child, timeout=5):
    """Stop the owned process group, including audio-route helpers."""
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        pass
    # The leader may have exited while a helper ignored TERM.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait()
