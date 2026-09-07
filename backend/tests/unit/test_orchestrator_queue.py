import threading
import time

import chaoxing.orchestrator as orch


def _fake_monitor():
    return type("FakeMonitor", (), {
        "__init__": lambda self, **kw: None,
        "start": lambda self: None,
        "stop": lambda self: None,
        "adjust_active_count": lambda self, n: None,
        "effective_estimate_gb": lambda self: 0.7,
    })


def test_queue_never_exceeds_slots(monkeypatch):
    max_seen = {"n": 0}
    lock = threading.Lock()
    barrier = threading.Barrier(3)

    def fake_run_for_account(account_index, creds, args):
        with lock:
            max_seen["n"] += 1
            max_seen["peak"] = max(max_seen.get("peak", 0), max_seen["n"])
        barrier.wait(timeout=5)
        time.sleep(0.05)
        with lock:
            max_seen["n"] -= 1

    monkeypatch.setattr(orch, "read_all_chaoxing_credentials",
                        lambda: [{"index": i, "account": f"a{i}", "password": "p"}
                                 for i in range(6)])
    monkeypatch.setattr(orch, "run_for_account", fake_run_for_account)
    monkeypatch.setattr(orch, "close_chaoxing_browser", lambda i: True)
    monkeypatch.setattr(orch, "MemoryMonitor", _fake_monitor())
    # Patch the names actually referenced inside orchestrator, not the
    # memory-module attributes (which the imported aliases do not follow).
    monkeypatch.setattr(orch, "measure_project_chrome_gb", lambda *a: 0.0)
    monkeypatch.setattr(orch, "gate_open", lambda *a: True)
    monkeypatch.setattr(orch, "_THREAD_STAGGER_SECONDS", 0)

    threads = orch.run_multi_account(
        account_indices=list(range(6)), mode="full",
        max_concurrent=3, budget_gb=2.0, system_limit_gb=20.0,
        per_account_estimate_gb=0.7,
    )
    assert len(threads) == 6
    assert max_seen["peak"] == 3


def test_queue_waits_when_gate_closed(monkeypatch):
    calls = {"gate": 0}

    def flaky_gate(*a):
        calls["gate"] += 1
        return calls["gate"] > 1

    monkeypatch.setattr(orch, "read_all_chaoxing_credentials",
                        lambda: [{"index": 0, "account": "a0", "password": "p"}])
    monkeypatch.setattr(orch, "run_for_account", lambda *a: None)
    monkeypatch.setattr(orch, "close_chaoxing_browser", lambda i: True)
    monkeypatch.setattr(orch, "MemoryMonitor", _fake_monitor())
    monkeypatch.setattr(orch, "measure_project_chrome_gb", lambda *a: 0.0)
    monkeypatch.setattr(orch, "gate_open", flaky_gate)
    monkeypatch.setattr(orch, "_GATE_RETRY_SECONDS", 0.01)

    threads = orch.run_multi_account(
        account_indices=[0], mode="full",
        max_concurrent=1, budget_gb=2.0, system_limit_gb=20.0,
        per_account_estimate_gb=0.7,
    )
    assert len(threads) == 1
