"""Hardware/OS report for CLAUDE.md and run metadata."""
from __future__ import annotations

import os
import platform
import sys


def collect() -> dict:
    info: dict = {"os": platform.platform(), "python": sys.version.split()[0], "machine": platform.machine(),
                  "cpu": platform.processor(), "logical_cpus": os.cpu_count()}
    try:
        import psutil
        info["physical_cpus"] = psutil.cpu_count(logical=False)
        info["ram_gb"] = round(psutil.virtual_memory().total / 2**30, 1)
    except Exception as e:
        info["psutil_error"] = repr(e)
    if sys.platform == "win32":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            info["cpu"] = winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        except Exception:
            pass
        try:
            import dxcam
            info["dxgi_devices"] = dxcam.device_info().strip()   # includes dedicated VRAM
            info["dxgi_outputs"] = dxcam.output_info().strip()
        except Exception as e:
            info["dxcam_error"] = repr(e)
        try:
            import win32api
            dm = win32api.EnumDisplaySettings(None, -1)  # ENUM_CURRENT_SETTINGS
            info["primary_display"] = f"{dm.PelsWidth}x{dm.PelsHeight} @ {dm.DisplayFrequency} Hz"
        except Exception as e:
            info["display_error"] = repr(e)
    try:
        import torch
        info["torch"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            info["cuda_device"] = f"{p.name}, {round(p.total_memory / 2**30, 1)} GB"
    except Exception:
        info["torch"] = "not installed"
    return info
