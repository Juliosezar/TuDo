"""Helpers for gathering local system information (Linux)."""

import os
import socket
import time


def get_hostname() -> str:
    return socket.gethostname()


def get_uptime() -> str:
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
        days = int(uptime_seconds // (24 * 3600))
        hours = int((uptime_seconds % (24 * 3600)) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        return f"{days}d {hours}h {minutes}m"
    except Exception:
        return "Unknown"


def get_cpu_percent(interval: float = 0.05) -> float:
    """
    Calculates CPU percentage over a very short window (50ms).
    This is 10x faster than psutil's default 500ms block.
    """
    try:

        def read_cpu_times():
            with open("/proc/stat", "r") as f:
                # The first line of /proc/stat represents total CPU times
                fields = [float(val) for val in f.readline().strip().split()[1:]]
            idle = fields[3] + fields[4]  # idle + iowait
            total = sum(fields)
            return idle, total

        idle1, total1 = read_cpu_times()
        time.sleep(interval)
        idle2, total2 = read_cpu_times()

        idle_delta = idle2 - idle1
        total_delta = total2 - total1

        if total_delta == 0:
            return 0.0
        return (1.0 - (idle_delta / total_delta)) * 100
    except Exception:
        return 0.0


def get_ram_info() -> tuple[float, float, float]:
    """Returns (used_gb, total_gb, percent)."""
    try:
        meminfo = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].replace(":", "")] = int(parts[1])

        total_kb = meminfo.get("MemTotal", 0)
        # MemAvailable represents free memory + reclaimable buffers/cache
        available_kb = meminfo.get("MemAvailable", total_kb - meminfo.get("MemFree", 0))
        used_kb = total_kb - available_kb

        total_gb = total_kb / (1024 * 1024)
        used_gb = used_kb / (1024 * 1024)
        percent = (used_kb / total_kb) * 100 if total_kb > 0 else 0
        return used_gb, total_gb, percent
    except Exception:
        return 0.0, 0.0, 0.0


def get_disk_usage(path: str) -> tuple[float, float, float]:
    """Returns (used_gb, total_gb, percent) for the given mount path."""
    try:
        # os.statvfs uses direct Linux system calls (extremely fast)
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free

        total_gb = total / (1024**3)
        used_gb = used / (1024**3)
        percent = (used / total) * 100 if total > 0 else 0
        return used_gb, total_gb, percent
    except Exception:
        return 0.0, 0.0, 0.0


DISK_PATHS = ["/", "/home"]
