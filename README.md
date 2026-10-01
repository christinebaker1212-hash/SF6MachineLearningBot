# SF6MachineLearningBot

Experimental machine-learning agent for Street Fighter 6 (Windows/Steam, Ryu, Classic controls).
Current stage: **Milestone 1: game connection** (screen capture, keyboard input, timing, recording, safety).

See [CLAUDE.md](CLAUDE.md) for architecture, install/run commands, the acceptance procedure,
verified vs. unverified capabilities, and next steps.

Quick start (Windows PowerShell):
```powershell
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e ".[windows,dev]"
sf6bot sysinfo
sf6bot list-windows
sf6bot capture-bench --seconds 20
```
Safety: **F8** stops and releases all inputs, **F7** pauses, and inputs release whenever SF6 loses focus.
