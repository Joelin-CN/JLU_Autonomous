"""
章节测试自动解答器 — Chapter Quiz Auto-Solver

Backward-compatible shim — delegates to chaoxing.solvers.quiz.
All real logic lives in chaoxing/solvers/quiz/solver.py.
"""
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from chaoxing.solvers.quiz.solver import ChapterQuizSolver
from chaoxing.solvers.quiz.stats import QuizStats


def main() -> None:
    """Legacy standalone entry is no longer supported."""
    print(
        "章节测验独立入口已移除；请改用 JSON-line 入口：\n"
        "  python -m chaoxing.api --job-id <id> --accounts <csv> --mode solve_only",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
