import math
import subprocess
import time

import pytest

from chaoxing.memory import (
    BUDGET_RATIO,
    EMERGENCY_CONSECUTIVE,
    EMERGENCY_MARGIN_GB,
    PER_ACCOUNT_INITIAL_GB,
    PROJECT_CAUSE_RATIO,
    EwmaTracker,
    MemorySamplerError,
    compute_plan,
    emergency_triggered,
    gate_open,
    measure_project_chrome_gb,
    measure_system_used_gb,
)


def test_compute_plan_matches_spec_example():
    plan = compute_plan(total_gb=31.8, baseline_gb=14.6, threads=32)
    assert plan["budget_gb"] == pytest.approx((31.8 - 14.6) * BUDGET_RATIO)
    assert plan["cpu_cap"] == 30
    assert plan["per_account_estimate_gb"] == PER_ACCOUNT_INITIAL_GB
    assert plan["mem_max"] == math.floor(
        plan["budget_gb"] / PER_ACCOUNT_INITIAL_GB)
    assert plan["max_concurrent"] == min(plan["mem_max"], plan["cpu_cap"])
    assert plan["system_limit_gb"] == pytest.approx(
        plan["baseline_gb"] + plan["budget_gb"] + EMERGENCY_MARGIN_GB)


def test_compute_plan_clamps_low_and_cpu_bound():
    plan = compute_plan(total_gb=8.0, baseline_gb=7.5, threads=4)
    assert plan["cpu_cap"] == 2
    assert plan["max_concurrent"] == min(plan["mem_max"], 2)
    assert plan["max_concurrent"] >= 1


def test_ewma_smooths_spike():
    t = EwmaTracker(alpha=0.3)
    assert t.update(0.5) == 0.5
    assert t.update(1.0) == pytest.approx(0.65)
    assert t.update(1.0) == pytest.approx(0.755)


def test_gate_open():
    assert gate_open(0.5, 2.0, 0.7) is True
    assert gate_open(1.4, 2.0, 0.7) is False


def test_emergency_requires_project_cause_and_consecutive_hits():
    assert emergency_triggered(15.0, 14.0, 0.5, 2.0, 5) is False
    assert emergency_triggered(15.0, 14.0, 2.0 * PROJECT_CAUSE_RATIO, 2.0,
                               EMERGENCY_CONSECUTIVE - 1) is False
    assert emergency_triggered(15.0, 14.0, 2.0 * PROJECT_CAUSE_RATIO, 2.0,
                               EMERGENCY_CONSECUTIVE) is True


def test_measure_project_chrome_parses_ps_output(monkeypatch):
    fake = subprocess.CompletedProcess([], 0, stdout="1234567890\n", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    assert measure_project_chrome_gb("C:\\profiles") == pytest.approx(
        1234567890 / 1024 ** 3)


def test_measure_project_chrome_no_process_returns_zero(monkeypatch):
    """No matching chrome.exe should report 0 GB, not a probe failure."""
    fake = subprocess.CompletedProcess([], 0, stdout="0\n", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    assert measure_project_chrome_gb("C:\\profiles") == 0.0


def test_measure_project_chrome_raises_on_failure(monkeypatch):
    fake = subprocess.CompletedProcess([], 1, stdout="", stderr="boom")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    with pytest.raises(MemorySamplerError):
        measure_project_chrome_gb("C:\\profiles")


def test_measure_system_used_gb(monkeypatch):
    fake = subprocess.CompletedProcess([], 0, stdout="14.6\n", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    assert measure_system_used_gb() == pytest.approx(14.6)


def test_monitor_thread_survives_sampler_exception(monkeypatch):
    """采样抛 TimeoutExpired（真机多 Chrome 时 CIM 查询 20s 超时）不得杀死监视线程。

    真机联测（2026-09-13）暴露：run() 原来只捕 MemorySamplerError，
    subprocess.TimeoutExpired 直接穿透导致线程死亡——后续 MEMORY 事件与
    急停判定全部失效。修复后任何采样异常只降级跳过本轮。
    """
    import chaoxing.memory as mem

    monkeypatch.setattr(mem, "SAMPLE_INTERVAL_S", 0.02)

    calls = {"n": 0}

    def flaky_measure(_root):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(cmd=["powershell"], timeout=20)
        return 0.5

    monkeypatch.setattr(mem, "measure_project_chrome_gb", flaky_measure)
    monkeypatch.setattr(mem, "measure_system_used_gb", lambda: 10.0)

    events = []
    mon = mem.MemoryMonitor(
        budget_gb=5.0, system_limit_gb=30.0, initial_estimate_gb=0.7,
        profile_root="X", on_event=events.append, on_emergency=lambda: None)
    mon.start()
    deadline = time.time() + 2
    while not events and time.time() < deadline:
        time.sleep(0.01)
    mon.stop()
    mon.join(timeout=1)

    assert calls["n"] >= 2, "第一轮异常后应继续采样"
    assert events, "采样异常被吞后，监视线程应继续发出 MEMORY 事件"
    assert events[0]["type"] == "MEMORY"
