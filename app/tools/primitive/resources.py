"""System resource tools — let agents check available RAM/VRAM/disk before loading models."""

from __future__ import annotations

import shutil
import subprocess

from app.tools import Tool
from app.config import SANDBOX_ROOT


def _get_resources() -> dict:
    """Gather RAM, disk, and GPU VRAM stats."""
    import os

    # RAM
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        ram = {
            "total_mb": mem.ullTotalPhys // (1024 * 1024),
            "available_mb": mem.ullAvailPhys // (1024 * 1024),
            "used_pct": mem.dwMemoryLoad,
        }
    except Exception:
        ram = {"total_mb": 0, "available_mb": 0, "used_pct": 0}

    # Disk
    try:
        usage = shutil.disk_usage(SANDBOX_ROOT)
        disk = {
            "total_gb": round(usage.total / (1024 ** 3), 1),
            "free_gb": round(usage.free / (1024 ** 3), 1),
        }
    except Exception:
        disk = {"total_gb": 0, "free_gb": 0}

    # GPU VRAM via nvidia-smi
    gpu = _get_gpu_info()

    return {"ram": ram, "disk": disk, "gpu": gpu}


def _get_gpu_info() -> list[dict]:
    """Query nvidia-smi for GPU memory. Returns empty list if unavailable."""
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return []
        gpus = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                gpus.append({
                    "index": int(parts[0]),
                    "name": parts[1],
                    "vram_total_mb": int(parts[2]),
                    "vram_used_mb": int(parts[3]),
                    "vram_free_mb": int(parts[4]),
                })
        return gpus
    except Exception:
        return []


def make_resource_tools() -> list[Tool]:
    async def check_resources() -> str:
        info = _get_resources()
        lines = []
        r = info["ram"]
        lines.append(f"RAM: {r['available_mb']}MB free / {r['total_mb']}MB total ({r['used_pct']}% used)")
        d = info["disk"]
        lines.append(f"Disk: {d['free_gb']}GB free / {d['total_gb']}GB total")
        for g in info["gpu"]:
            lines.append(
                f"GPU {g['index']} ({g['name']}): "
                f"{g['vram_free_mb']}MB VRAM free / {g['vram_total_mb']}MB total "
                f"({g['vram_used_mb']}MB used)"
            )
        if not info["gpu"]:
            lines.append("GPU: No NVIDIA GPU detected (nvidia-smi unavailable)")
        return "\n".join(lines)

    return [
        Tool("check_resources", "Check available system resources (RAM, disk, GPU VRAM). Use before loading large models.", {
            "type": "object",
            "properties": {},
            "required": [],
        }, check_resources),
    ]
