"""智慧树 JSON-line 协议入口（M2：登录态 + 课程/章节扫描）。

与超星 platforms.chaoxing.api 同一 NDJSON 协议（PROGRESS/PHASE/LOG/TICKET/
RESULT/ERROR/DONE + stdin PAUSE/RESUME/STOP）。M2 仅实现 scan_only 与
full 的扫描阶段；视频/答题为 M3/M4。

用法：
    python -m platforms.zhihuishu.api --job-id j1 --accounts 0 --mode scan_only
"""

import argparse
import json
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from core.constants import OUTPUT_DIR, SHUTDOWN_FLAG
from core.logging_setup import (
    set_protocol_handler, signal_pause, signal_resume, signal_stop,
    log as core_log,
)
# 内存治理钩子：作为模块属性被 core.orchestrator.ModuleRunner 惰性读取
from core.memory import (
    MemoryMonitor, gate_open, measure_project_chrome_gb,
    PER_ACCOUNT_INITIAL_GB,
)
from core.session import set_active_session

from platforms.zhihuishu.auth import (
    SESSION_PREFIX, ensure_logged_in, close_zhihuishu_browser,
    read_all_zhihuishu_credentials,
)
from platforms.zhihuishu.scanner import scan_courses, scan_course_sections

VALID_PHASES = ("idle", "login", "scan_courses", "completed",
                "paused", "stopped", "error")

_stdout_lock = threading.Lock()
_job_id = ""
_current_phase = "idle"


def _write_json_line(obj: dict) -> None:
    obj.setdefault("jobId", _job_id)
    line = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    with _stdout_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _emit_phase(phase: str) -> None:
    global _current_phase
    _current_phase = phase
    _write_json_line({"type": "PHASE", "phase": phase})


def _emit_progress(percent, message, account_id=None):
    payload = {"type": "PROGRESS", "percent": percent, "message": message}
    if account_id is not None:
        payload["accountId"] = account_id
    _write_json_line(payload)


def _emit_result(data):
    _write_json_line({"type": "RESULT", "data": data})


def _emit_error(error, stack=None):
    payload = {"type": "ERROR", "error": error}
    if stack:
        payload["stack"] = stack
    _write_json_line(payload)


def _protocol_handler(event: dict) -> None:
    et = event.get("type", "")
    if et == "LOG":
        _write_json_line({
            "type": "LOG", "level": event.get("level", "info"),
            "message": event["message"],
            "timestamp": datetime.now(timezone.utc).isoformat(
                timespec="milliseconds").replace("+00:00", "Z"),
        })
    elif et == "PROGRESS":
        _emit_progress(event.get("percent", 0), event.get("message", ""),
                       event.get("accountId"))
    elif et == "PHASE":
        if event.get("phase") in VALID_PHASES:
            _emit_phase(event["phase"])
    elif et == "TICKET":
        if isinstance(event.get("ticket"), dict):
            _write_json_line({"type": "TICKET", "ticket": event["ticket"]})
    elif et == "MEMORY":
        # core.memory.MemoryMonitor 的快照（预算仪表数据源）；缺此分支会被静默丢弃
        _write_json_line(event)


def _start_stdin_controller() -> threading.Thread:
    def loop():
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            cmd = line.strip().upper()
            if cmd == "PAUSE":
                signal_pause()
                _emit_phase("paused")
            elif cmd == "RESUME":
                signal_resume()
                _emit_phase(_current_phase if _current_phase != "paused"
                            else "scan_courses")
            elif cmd == "STOP":
                signal_stop()
                _emit_phase("stopped")
                break
    t = threading.Thread(target=loop, name="zhihuishu-stdin", daemon=True)
    t.start()
    return t


def _save_discovered(account_index: int, courses: list[dict]) -> Path:
    out = OUTPUT_DIR / f"discovered_courses_{SESSION_PREFIX}-{account_index}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(courses, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return out




# ── core 编排机钩子（多账号并发/内存门，见 core.orchestrator）────────

SESSION_PREFIX = SESSION_PREFIX           # zhihuishu-chrome（会话/线程命名）
THREAD_PREFIX = "zhihuishu-account"


class RunConfig:
    """智慧树任务配置（与超星 RunConfig 同构的最小集）。"""

    def __init__(self, *, course=None, dry_run=False, resume=False,
                 scan_only=False, quiz_only=False, content_only=False,
                 grade_only=False, yes=True, mode="scan_only"):
        self.course = course
        self.dry_run = dry_run
        self.resume = resume
        self.scan_only = scan_only
        self.quiz_only = quiz_only
        self.content_only = content_only
        self.grade_only = grade_only
        self.yes = yes
        self.mode = mode


def config_cls(**kwargs):
    return RunConfig(**kwargs)


def run_account(account_index: int, creds: dict, config) -> bool:
    return _run_account(account_index, creds, config)


def read_credentials():
    return read_all_zhihuishu_credentials()


def close_browser(account_index: int):
    close_zhihuishu_browser(account_index)


def session_name(account_index: int) -> str:
    return f"{SESSION_PREFIX}-{account_index}"


def thread_name(account_index: int) -> str:
    return f"{THREAD_PREFIX}-{account_index}"


def progress(account_index, message, *args, lane_status=None):
    _emit_progress(None, message, account_index)


def max_concurrent_cfg():
    try:
        from core.config import get_config
        return get_config().max_concurrent
    except Exception:
        return None


def _run_account(account_index: int, creds: dict, config) -> bool:
    mode = getattr(config, "mode", "scan_only")
    session = f"{SESSION_PREFIX}-{account_index}"
    set_active_session(session)

    _emit_progress(5, "检查登录态...", account_index)
    if not ensure_logged_in(account_index):
        _emit_progress(0, "登录失败", account_index)
        return False
    _emit_progress(20, "已登录", account_index)

    _emit_phase("scan_courses")
    courses = scan_courses()
    if not courses:
        _emit_progress(100, "未发现共享课", account_index)
        return True

    # 逐课解析章节树（扫描阶段核心）
    for i, c in enumerate(courses):
        if SHUTDOWN_FLAG.is_set():
            break
        _emit_progress(
            20 + int(70 * (i / len(courses))),
            f"扫描章节：{c['name']}（{i + 1}/{len(courses)}）", account_index)
        tree = scan_course_sections(c["recruitId"], c["courseId"])
        c["chapters"] = tree["chapters"] if tree else []
        c["quiz_sections"] = tree["quiz_sections"] if tree else []
        c["total_sections"] = sum(len(ch["sections"]) for ch in c["chapters"])
        c["remaining_sections"] = [
            {"chapter": ch["name"], **s}
            for ch in c["chapters"] for s in ch["sections"]
            if s["kind"] == "video" and not s.get("finished")
        ]
        time.sleep(1.0)

    path = _save_discovered(account_index, courses)
    core_log(f"Account {account_index}：发现 {len(courses)} 门课，"
             f"状态已存 {path.name}")
    _emit_progress(95, f"扫描完成：{len(courses)} 门课", account_index)

    if mode != "scan_only":
        # M3：视频章节自动完成（D6 决策——仅 1.0 倍速真实播放，全程类人操作）
        from platforms.zhihuishu.video import ZhihuishuVideoBot
        for i, c in enumerate(courses):
            if SHUTDOWN_FLAG.is_set():
                break
            remaining = len(c.get("remaining_sections", []))
            if not remaining:
                continue
            core_log(f"Account {account_index}：开始视频 {c['name']}"
                     f"（待看 {remaining} 节，原速真实播放）")
            _emit_progress(95, f"视频学习：{c['name']}", account_index)
            ZhihuishuVideoBot(c).run()
            # 处理完重扫一次进度（复用扫描链路）
            tree = scan_course_sections(c["recruitId"], c["courseId"])
            if tree:
                c["chapters"] = tree["chapters"]
                c["remaining_sections"] = [
                    {"chapter": ch["name"], **s}
                    for ch in c["chapters"] for s in ch["sections"]
                    if s["kind"] == "video" and not s.get("finished")
                ]
        _save_discovered(account_index, courses)
    return True


def main() -> None:
    global _job_id
    parser = argparse.ArgumentParser(
        description="Zhihuishu Backend API -- JSON-line protocol (M2: login + scan)")
    parser.add_argument("--job-id", type=str, required=True)
    parser.add_argument("--accounts", type=str, required=True,
                        help="Comma-separated account indices")
    parser.add_argument("--mode", type=str, default="scan_only",
                        choices=["scan_only", "full", "solve_only"])
    parser.add_argument(
        "--max-concurrent", type=int, default=None,
        help="Runtime size of the account semaphore (Electron computes this "
             "from the memory/CPU plan; CLI runs fall back to config).")
    parser.add_argument(
        "--budget-gb", type=float, default=None,
        help="Project memory budget in GB (Electron-computed).")
    parser.add_argument(
        "--system-limit-gb", type=float, default=None,
        help="Absolute system-used-RAM emergency threshold in GB "
             "(baseline + budget + margin, Electron-computed).")
    parser.add_argument(
        "--per-account-estimate-gb", type=float, default=None,
        help="Initial per-Chrome memory estimate in GB (default 0.7).")
    cli = parser.parse_args()

    _job_id = cli.job_id
    stdin_thread = _start_stdin_controller()
    set_protocol_handler(_protocol_handler)

    if cli.system_limit_gb:
        from core.logging_setup import set_ram_limit_gb
        set_ram_limit_gb(float(cli.system_limit_gb))

    indices = sorted({int(s) for s in cli.accounts.split(",") if s.strip().isdigit()})
    if not indices:
        _emit_error("No valid account indices")
        _write_json_line({"type": "DONE"})
        return

    creds = read_all_zhihuishu_credentials()
    if not creds:
        _emit_error("No accounts found in data/passwords/zhihuishu.txt")
        _write_json_line({"type": "DONE"})
        return
    missing = set(indices) - {c["index"] for c in creds}
    if missing:
        _emit_error(f"Account indices not found: {sorted(missing)}")
        _write_json_line({"type": "DONE"})
        return

    _emit_phase("idle")
    _emit_progress(0, f"Job {cli.job_id} starting -- mode={cli.mode}, accounts={indices}")
    start = time.time()
    import sys as _sys
    from core.orchestrator import ModuleRunner, run_multi_account_generic, AccountRunError
    try:
        _emit_phase("login")
        run_multi_account_generic(
            ModuleRunner(_sys.modules[__name__]), indices, mode=cli.mode,
            max_concurrent=cli.max_concurrent, budget_gb=cli.budget_gb,
            system_limit_gb=cli.system_limit_gb,
            per_account_estimate_gb=cli.per_account_estimate_gb)
        if SHUTDOWN_FLAG.is_set():
            _emit_phase("stopped")
            _emit_error(f"Job stopped by user after {time.time() - start:.0f}s")
        else:
            _emit_phase("completed")
            _emit_progress(100, f"All accounts scanned in {time.time() - start:.0f}s")
            _emit_result({"success": True,
                          "durationMs": int((time.time() - start) * 1000),
                          "accountsProcessed": len(indices), "mode": cli.mode})
    except AccountRunError as e:
        _emit_phase("error")
        _emit_error(str(e))
    except Exception as e:
        _emit_phase("error")
        _emit_error(str(e), stack=traceback.format_exc())
    finally:
        for idx in indices:
            try:
                close_zhihuishu_browser(idx)
            except Exception:
                pass
        set_protocol_handler(None)
        SHUTDOWN_FLAG.clear()
        _write_json_line({"type": "DONE"})


if __name__ == "__main__":
    main()
