"""
章节内容自动完成机器人 — Chapter Content Auto-Completion Bot

Backward-compatible shim — delegates to chaoxing.solvers.content.
All real logic lives in chaoxing/solvers/content/bot.py.
"""
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from chaoxing.solvers.content.bot import ChapterContentBot, ProgressTracker


def main() -> None:
    """Legacy standalone entry is no longer supported."""
    print(
        "内容完成独立入口已移除；请改用 JSON-line 入口：\n"
        "  python -m chaoxing.api --job-id <id> --accounts <csv> --mode full --content-only",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
