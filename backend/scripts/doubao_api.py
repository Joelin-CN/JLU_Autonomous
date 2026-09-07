"""
Doubao (豆包) API Quiz Solver — Volcano Ark / 火山方舟

Backward-compatible shim — delegates to chaoxing.ai.doubao.
All real logic lives in chaoxing/ai/doubao.py.
"""
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from chaoxing.ai.doubao import (
    DoubaoAPISolver,
    doubao_solve_quiz,
    doubao_solve_quiz_image,
    doubao_ask_image,
)
