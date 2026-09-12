"""Memory budgeting, sampling, and the runtime monitor."""

import subprocess
import sys
import threading
from typing import Optional

from .constants import CHROME_PROFILES_DIR, SHUTDOWN_FLAG
from .logging_setup import log, signal_stop

BUDGET_RATIO = 0.75
PER_ACCOUNT_INITIAL_GB = 0.7
EMERGENCY_MARGIN_GB = 1.0
SAMPLE_INTERVAL_S = 5
EMERGENCY_CONSECUTIVE = 2
PROJECT_CAUSE_RATIO = 0.95


class MemorySamplerError(RuntimeError):
    """Raised when a platform memory probe cannot run or parse."""


def compute_plan(total_gb: float, baseline_gb: float, threads: int,
                 per_account_estimate_gb: Optional[float] = None) -> dict:
    estimate = float(per_account_estimate_gb or PER_ACCOUNT_INITIAL_GB)
    budget_gb = (total_gb - baseline_gb) * BUDGET_RATIO
    cpu_cap = max(2, int(threads) - 2)
    mem_max = max(1, int(budget_gb // estimate))
    max_concurrent = max(1, min(mem_max, cpu_cap))
    return {
        "total_gb": float(total_gb),
        "baseline_gb": float(baseline_gb),
        "budget_gb": budget_gb,
        "cpu_cap": cpu_cap,
        "mem_max": mem_max,
        "max_concurrent": max_concurrent,
        "system_limit_gb": baseline_gb + budget_gb + EMERGENCY_MARGIN_GB,
        "per_account_estimate_gb": estimate,
    }


class EwmaTracker:
    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.value = 0.0

    def update(self, value: float) -> float:
        self.value = value if self.value == 0.0 else (
            self.alpha * value + (1 - self.alpha) * self.value)
        return self.value


def gate_open(project_chrome_gb: float, budget_gb: float,
              effective_estimate_gb: float) -> bool:
    return (project_chrome_gb + effective_estimate_gb) <= budget_gb


def emergency_triggered(system_used_gb: float, system_limit_gb: float,
                        project_chrome_gb: float, budget_gb: float,
                        consecutive_hits: int) -> bool:
    if consecutive_hits < EMERGENCY_CONSECUTIVE:
        return False
    if system_used_gb < system_limit_gb:
        return False
    return project_chrome_gb >= budget_gb * PROJECT_CAUSE_RATIO


def _run_ps(script: str, timeout: int = 20) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise MemorySamplerError(
            f"PowerShell probe failed: {(result.stderr or '').strip()[:200]}")
    return result.stdout.strip()


def measure_project_chrome_gb(profile_root: str = None) -> float:
    if sys.platform != "win32":
        raise MemorySamplerError("Chrome-tree sampling only implemented on Windows")
    root = profile_root or str(CHROME_PROFILES_DIR)
    escaped = root.replace("'", "''")
    script = (
        "$p = Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\";"
        f"$m = $p | Where-Object {{ $_.CommandLine -like '*{escaped}*' }};"
        "$s = ($m | Measure-Object -Property WorkingSetSize -Sum).Sum;"
        "if ($null -eq $s) { $s = 0 };"
        "[Console]::Out.Write([string]($s))"
    )
    return float(_run_ps(script)) / (1024 ** 3)


def measure_system_used_gb() -> float:
    if sys.platform != "win32":
        raise MemorySamplerError("System RAM sampling only implemented on Windows")
    script = (
        "$os = Get-CimInstance Win32_OperatingSystem;"
        "$cs = Get-CimInstance Win32_ComputerSystem;"
        "$used = ($cs.TotalPhysicalMemory - ($os.FreePhysicalMemory * 1024));"
        "[Console]::Out.Write([string]([math]::Round($used/1GB, 3)))"
    )
    return float(_run_ps(script))


class MemoryMonitor(threading.Thread):
    """Samples memory every SAMPLE_INTERVAL_S and emits MEMORY events."""

    def __init__(self, *, budget_gb: float, system_limit_gb: float,
                 initial_estimate_gb: float, profile_root: str,
                 on_event, on_emergency):
        super().__init__(name="chaoxing-memory-monitor", daemon=True)
        self.budget_gb = budget_gb
        self.system_limit_gb = system_limit_gb
        self.initial_estimate_gb = initial_estimate_gb
        self.profile_root = profile_root
        self.on_event = on_event
        self.on_emergency = on_emergency
        self.ewma = EwmaTracker()
        self.active_count = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._consecutive = 0
        self._emergency_fired = False

    def set_active_count(self, count: int) -> None:
        with self._lock:
            self.active_count = max(0, count)

    def adjust_active_count(self, delta: int) -> None:
        with self._lock:
            self.active_count = max(0, self.active_count + delta)

    def stop(self) -> None:
        self._stop.set()

    def effective_estimate_gb(self) -> float:
        return max(self.initial_estimate_gb, self.ewma.value)

    def run(self) -> None:
        while not self._stop.wait(SAMPLE_INTERVAL_S):
            try:
                project_gb = measure_project_chrome_gb(self.profile_root)
                system_gb = measure_system_used_gb()
            except MemorySamplerError as e:
                log(f"Memory sampler degraded: {e}", "WARN")
                continue
            with self._lock:
                active = self.active_count
            avg = project_gb / active if active > 0 else self.initial_estimate_gb
            self.ewma.update(avg)
            if emergency_triggered(system_gb, self.system_limit_gb,
                                   project_gb, self.budget_gb,
                                   self._consecutive):
                self._consecutive += 1
            else:
                self._consecutive = 0
            if self._consecutive >= EMERGENCY_CONSECUTIVE and not self._emergency_fired:
                self._emergency_fired = True
                log("EMERGENCY: memory budget exceeded and not receding", "ERROR")
                signal_stop()
                SHUTDOWN_FLAG.set()
                self.on_emergency()
            remaining = max(0, int((self.budget_gb - project_gb)
                                   // self.effective_estimate_gb()))
            self.on_event({
                "type": "MEMORY",
                "budgetGB": round(self.budget_gb, 2),
                "projectChromeGB": round(project_gb, 2),
                "perAccountAvgGB": round(self.ewma.value, 2),
                "remainingCount": remaining,
                "level": "critical" if self._emergency_fired else "info",
                "message": f"project={project_gb:.2f}GB avg={self.ewma.value:.2f}GB",
            })
