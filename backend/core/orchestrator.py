"""平台无关的多账号编排机（信号量并发 + 内存门 + 泳道结果收集）。

从超星 orchestrator 抽取的通用机制；平台差异通过 ``ModuleRunner`` 以
**惰性 getattr** 挂到平台模块上——运行时读取模块属性，因此测试对平台
模块的 monkeypatch（run_for_account / close_browser / MemoryMonitor /
measure_project_chrome_gb / gate_open / 常量…）对本机制同样生效。

平台模块需提供的属性面（见 ``RUNNER_ATTRS``）：
    read_credentials() -> list[dict]        凭据列表（含 index）
    run_account(idx, creds, config)         单账号全流程（登录→扫描→处理）
    close_browser(idx)                      收尾关闭浏览器会话
    session_name(idx) / thread_name(idx)    命名（可选，默认 {prefix}-chrome-N）
    config_cls                              RunConfig 类（线程参数 [2] 位置约定）
    MemoryMonitor / measure_project_chrome_gb / gate_open   内存治理钩子
    PER_ACCOUNT_INITIAL_GB                  初始内存估计（可选）
    _THREAD_STAGGER_SECONDS / _GATE_RETRY_SECONDS           节奏常量（可选）
    log                                     日志函数
"""

import threading
import time
from typing import Any, Callable

from core.constants import SHUTDOWN_FLAG, CHROME_PROFILES_DIR
from core.logging_setup import log as _core_log, emit_memory
from core.utils import human_delay

# 平台模块必须/可选提供的属性名
_REQUIRED = ("read_credentials", "run_account", "close_browser", "config_cls")
_OPTIONAL = {
    "session_name": None, "thread_name": None,
    "MemoryMonitor": None, "measure_project_chrome_gb": None,
    "gate_open": None, "PER_ACCOUNT_INITIAL_GB": 0.7,
    "_THREAD_STAGGER_SECONDS": 0.5, "_GATE_RETRY_SECONDS": 5.0,
    "log": _core_log,
}


class ModuleRunner:
    """Lazy view over a platform module's orchestration hooks."""

    def __init__(self, module) -> None:
        self._module = module
        missing = [a for a in _REQUIRED if not hasattr(module, a)]
        if missing:
            raise AttributeError(
                f"platform module {module.__name__} lacks runner hooks: {missing}")

    def get(self, name: str, default: Any = None) -> Any:
        """Resolve a hook from the platform module at CALL time (patchable)."""
        if hasattr(self._module, name):
            return getattr(self._module, name)
        if name in _OPTIONAL:
            return _OPTIONAL[name]
        return default

    # ── convenience accessors ──
    @property
    def log(self) -> Callable:
        return self.get("log", _core_log)


class AccountRunError(RuntimeError):
    """Raised when one or more account lanes finished with a hard failure."""


def _default_session_name(platform_module, idx: int) -> str:
    fn = getattr(platform_module, "session_name", None)
    if fn:
        return fn(idx)
    return getattr(platform_module, "SESSION_PREFIX", "chaoxing") + f"-chrome-{idx}"


def _default_thread_name(platform_module, idx: int) -> str:
    fn = getattr(platform_module, "thread_name", None)
    if fn:
        return fn(idx)
    return getattr(platform_module, "THREAD_PREFIX",
                   getattr(platform_module, "SESSION_PREFIX", "chaoxing")) \
        + f"-account-{idx}"


def run_account_in_thread(runner: ModuleRunner, account_index: int, creds: dict,
                          config, semaphore, monitor, budget_gb,
                          initial_estimate_gb, results=None, results_lock=None):
    """Thread target: memory-gated execution of one account lane.

    Waits on the runtime-sized semaphore, then checks the live memory budget
    before opening a browser. All platform hooks are resolved lazily through
    ``runner`` so monkeypatched module attributes take effect.
    """
    module = runner._module
    log = runner.log
    stagger = None  # unused here; kept for signature parity with older callers
    progress = runner.get("progress")
    thread_name = _default_thread_name(module, account_index)
    threading.current_thread().name = thread_name
    if progress:
        progress(account_index, "Queued (waiting for a slot)", lane_status="queued")

    semaphore.acquire()
    try:
        if SHUTDOWN_FLAG.is_set():
            if progress:
                progress(account_index, "Skipped (shutdown)", lane_status="error")
            _record_result(results, results_lock, account_index,
                           ok=True, reason="skipped (shutdown)")
            return

        measure = runner.get("measure_project_chrome_gb")
        gate = runner.get("gate_open")
        gate_retry = float(runner.get("_GATE_RETRY_SECONDS", 5.0))
        if budget_gb is not None and measure and gate:
            class _SamplerError(Exception):
                pass
            while not SHUTDOWN_FLAG.is_set():
                try:
                    project_gb = measure()
                except Exception:
                    project_gb = 0.0
                est = monitor.effective_estimate_gb() if monitor \
                    else initial_estimate_gb
                if gate(project_gb, budget_gb, est):
                    break
                log(f"Account {account_index}: memory budget full, waiting...",
                    "WARN")
                time.sleep(gate_retry)
            if SHUTDOWN_FLAG.is_set():
                if progress:
                    progress(account_index, "Skipped (shutdown)", lane_status="error")
                _record_result(results, results_lock, account_index,
                               ok=True, reason="skipped (shutdown)")
                return

        if monitor:
            monitor.adjust_active_count(+1)
        if progress:
            progress(account_index, "Starting", lane_status="running")
        ok = runner.get("run_account")(account_index, creds, config)
        _record_result(results, results_lock, account_index,
                       ok=ok is not False,
                       reason=None if ok is not False else "login failed")
    except KeyboardInterrupt:
        log("Interrupted by user", "WARN")
        SHUTDOWN_FLAG.set()
        _record_result(results, results_lock, account_index,
                       ok=True, reason="stopped by user")
    except Exception as e:
        log(f"Fatal error in thread for account {account_index}: {e}", "ERROR")
        exc_hook = runner.get("log_exception")
        if exc_hook:
            exc_hook(f"Account {account_index}: thread crash", exc=e)
        if progress:
            progress(account_index, "FAILED", lane_status="error")
        _record_result(results, results_lock, account_index,
                       ok=False, reason=str(e))
    finally:
        if monitor:
            monitor.adjust_active_count(-1)
        try:
            runner.get("close_browser")(account_index)
        except Exception as e:
            log(f"Account {account_index}: browser close failed: {e}", "WARN")
        semaphore.release()


def _record_result(results, results_lock, account_index: int, ok: bool, reason):
    if results is None:
        return
    with results_lock:
        results.append({"accountIndex": account_index, "ok": ok, "reason": reason})


def run_multi_account_generic(runner: ModuleRunner, account_indices: list,
                              mode: str = "full", course: str = None,
                              grade_only: bool = False, content_only: bool = False,
                              dry_run: bool = False, resume: bool = False,
                              max_concurrent: int = None, budget_gb: float = None,
                              system_limit_gb: float = None,
                              per_account_estimate_gb: float = None):
    """Run multiple account lanes in parallel threads (platform-agnostic).

    Returns the list of thread objects (all completed); raises AccountRunError
    when any lane failed hard and the run was not user-stopped.
    """
    module = runner._module
    log = runner.log
    read_credentials = runner.get("read_credentials")

    all_creds = read_credentials()
    if not all_creds:
        log("No accounts found in credentials file", "ERROR")
        return []

    indices_set = set(account_indices)
    accounts_to_run = [c for c in all_creds if c["index"] in indices_set]
    missing = indices_set - {c["index"] for c in accounts_to_run}
    if missing:
        log(f"Account indices not found: {sorted(missing)}", "WARN")
    if not accounts_to_run:
        log("No matching accounts to run", "ERROR")
        return []

    config_cls = runner.get("config_cls")
    config = config_cls(
        course=course, dry_run=dry_run, resume=resume,
        scan_only=(mode == "scan_only"), quiz_only=(mode == "solve_only"),
        content_only=content_only, grade_only=grade_only, yes=True)

    log(f"\nMulti-account mode: {len(accounts_to_run)} account(s) to process")
    log(f"Mode: {mode}, Course filter: {course or 'none'}")
    log(f"Spawning {len(accounts_to_run)} parallel thread(s)...")

    SHUTDOWN_FLAG.clear()
    max_concurrent_cfg = runner.get("max_concurrent_cfg")
    if callable(max_concurrent_cfg):
        max_concurrent_cfg = max_concurrent_cfg()
    slots = max(1, int(max_concurrent or max_concurrent_cfg or 1))
    semaphore = threading.BoundedSemaphore(slots)
    initial_estimate = float(
        per_account_estimate_gb or runner.get("PER_ACCOUNT_INITIAL_GB", 0.7))

    monitor = None
    monitor_cls = runner.get("MemoryMonitor")
    if system_limit_gb and monitor_cls:
        monitor = monitor_cls(
            budget_gb=float(budget_gb) if budget_gb else float(system_limit_gb),
            system_limit_gb=float(system_limit_gb),
            initial_estimate_gb=initial_estimate,
            profile_root=str(CHROME_PROFILES_DIR),
            on_event=emit_memory,
            on_emergency=lambda: None,
        )
        monitor.start()

    stagger = float(runner.get("_THREAD_STAGGER_SECONDS", 0.5))
    threads = []
    results: list = []
    results_lock = threading.Lock()
    try:
        for cred in accounts_to_run:
            t = threading.Thread(
                target=run_account_in_thread,
                args=(runner, cred["index"], cred, config, semaphore, monitor,
                      budget_gb, initial_estimate, results, results_lock),
                name=_default_thread_name(module, cred["index"]),
                daemon=False,
            )
            t.start()
            threads.append(t)
            log(f"Started thread for account [{cred['index']}]")
            human_delay(stagger, 0.5)

        try:
            for t in threads:
                while t.is_alive():
                    t.join(timeout=1.0)
        except KeyboardInterrupt:
            log("\n[!] Ctrl+C received. Signaling all threads to stop...", "WARN")
            SHUTDOWN_FLAG.set()
            for t in threads:
                t.join(timeout=10.0)
            log("All threads stopped (or timed out after 10s).")
    except KeyboardInterrupt:
        log("\n[!] Ctrl+C received. Signaling all threads to stop...", "WARN")
        SHUTDOWN_FLAG.set()
        for t in threads:
            t.join(timeout=10.0)
        log("All threads stopped (or timed out after 10s).")
    finally:
        if monitor:
            monitor.stop()

    if not SHUTDOWN_FLAG.is_set():
        failures = [r for r in results if not r["ok"]]
        if failures:
            detail = "; ".join(
                f"account {r['accountIndex']} ({r['reason'] or 'unknown error'})"
                for r in failures)
            raise AccountRunError(f"{len(failures)} account(s) failed: {detail}")

    log(f"\n{'='*60}")
    log(f"Multi-account run complete. {len(threads)} account(s) processed.")
    log(f"{'='*60}")
    return threads
