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


def _run_account(account_index: int, mode: str) -> bool:
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
        core_log("视频/答题处理为 M3/M4 范围，本次仅完成扫描", "WARN")
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
    cli = parser.parse_args()

    _job_id = cli.job_id
    stdin_thread = _start_stdin_controller()
    set_protocol_handler(_protocol_handler)

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
    ok_all = True
    try:
        _emit_phase("login")
        for idx in indices:
            ok_all = _run_account(idx, cli.mode) and ok_all
        if SHUTDOWN_FLAG.is_set():
            _emit_phase("stopped")
            _emit_error(f"Job stopped by user after {time.time() - start:.0f}s")
        elif ok_all:
            _emit_phase("completed")
            _emit_progress(100, f"All accounts scanned in {time.time() - start:.0f}s")
            _emit_result({"success": True,
                          "durationMs": int((time.time() - start) * 1000),
                          "accountsProcessed": len(indices), "mode": cli.mode})
        else:
            _emit_phase("error")
            _emit_error("One or more accounts failed (see LOG events)")
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
