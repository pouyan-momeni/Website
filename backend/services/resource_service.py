"""Service for monitoring system resources via psutil."""

import psutil

from backend.schemas.schemas import ResourceSnapshot


def get_snapshot() -> ResourceSnapshot:
    """
    Get a snapshot of current system resource usage.
    Returns CPU%, memory%, disk% with total and used values in GB.
    """
    cpu_percent = psutil.cpu_percent(interval=0.5)

    mem = psutil.virtual_memory()
    memory_percent = mem.percent
    memory_total_gb = round(mem.total / (1024 ** 3), 2)
    memory_used_gb = round(mem.used / (1024 ** 3), 2)

    disk = psutil.disk_usage("/")
    disk_percent = disk.percent
    disk_total_gb = round(disk.total / (1024 ** 3), 2)
    disk_used_gb = round(disk.used / (1024 ** 3), 2)

    return ResourceSnapshot(
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        memory_total_gb=memory_total_gb,
        memory_used_gb=memory_used_gb,
        disk_percent=disk_percent,
        disk_total_gb=disk_total_gb,
        disk_used_gb=disk_used_gb,
    )
