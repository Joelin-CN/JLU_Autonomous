"""智慧树已发现课程查询子命令（读 discovered_courses_zhihuishu-chrome-N.json）。

输出与超星 courses 同构的单行 JSON：{type: "COURSES", scanned, courses}。
"""

import argparse
import json
import sys
from pathlib import Path

from core.constants import OUTPUT_DIR

from platforms.zhihuishu.auth import SESSION_PREFIX


def _write(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def _discovered_file(account_index: int) -> Path:
    return OUTPUT_DIR / f"discovered_courses_{SESSION_PREFIX}-{account_index}.json"


def _map_course(raw: dict, account_index: int) -> dict:
    remaining = raw.get("remaining_sections", [])
    done = raw.get("total_sections", 0) - len(remaining)
    return {
        "accountIndex": account_index,
        "platform": "zhihuishu",
        "courseId": raw.get("courseId", ""),
        "recruitId": raw.get("recruitId", ""),
        "name": raw.get("name", ""),
        "teacher": raw.get("teacher", ""),
        "progress": raw.get("progress", ""),
        "totalSections": raw.get("total_sections", 0),
        "remainingSections": len(remaining),
        "quizSections": len(raw.get("quiz_sections", [])),
        "status": "completed" if not remaining else "in-progress",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="List discovered zhihuishu courses")
    parser.add_argument("--account", type=int, default=0)
    args = parser.parse_args()

    path = _discovered_file(args.account)
    if not path.exists():
        _write({"type": "ERROR",
                "error": f"No discovery state for account {args.account}",
                "hint": "先运行 platforms.zhihuishu.api --mode scan_only"})
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        _write({"type": "ERROR", "error": f"读取失败：{e}"})
        return
    # discovered 文件存的是课程数组（与超星 discover 状态一致）
    if isinstance(raw, dict):
        raw = raw.get("courses", [])
    _write({"type": "COURSES", "scanned": "",
            "courses": [_map_course(c, args.account) for c in raw]})


if __name__ == "__main__":
    main()
