"""
5-tier solving strategies — ordered fallback chain for quiz solving.

Each strategy attempts to extract answers from a quiz page using a different
approach. Tier 1 (font decrypt) is fastest/cheapest; Tier 5 (snapshot text)
is the last resort. The chain stops at the first strategy that succeeds.

Strategy order:
    1. FontDecryptTextStrategy  — decrypt font-cxsecret, send text to AI
    2. V2ScreenshotStrategy     — element.screenshot() each .TiMu container
    3. V1ScreenshotStrategy     — clip-based per-question screenshots
    4. FullPageScreenshotStrategy — single full-body screenshot
    5. SnapshotTextStrategy     — YAML snapshot text extraction
"""

from abc import ABC, abstractmethod

from ...logging_setup import log


class SolvingStrategy(ABC):
    """Abstract base for a quiz-solving strategy.

    Each concrete strategy must provide:
        name: Human-readable strategy name.
        tier: Priority order (1 = best, 5 = last resort).
        try_solve(solver) -> dict | None:
            Attempt to solve the quiz. Returns a result dict on success:
                {"answers": list[dict], "q_count": int, "mode": str, "q_infos": list[dict] | None}
            Returns None on failure (caller tries the next strategy).
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def tier(self) -> int: ...

    @abstractmethod
    def try_solve(self, solver) -> dict | None:
        """Attempt to solve the quiz. Returns result dict or None."""
        ...


class FontDecryptTextStrategy(SolvingStrategy):
    """Tier 1: Decrypt font-cxsecret obfuscation, send clean text to AI.

    Fastest and cheapest — no screenshots needed. Falls back if font
    decryption produces garbled output (>30% rare Unicode chars).
    """

    @property
    def name(self) -> str:
        return "FontDecryptText"

    @property
    def tier(self) -> int:
        return 1

    def try_solve(self, solver) -> dict | None:
        from ...font import get_decrypted_quiz_text
        from ..quiz.extractor import count_questions_in_text

        try:
            decrypted_text = get_decrypted_quiz_text()
            if not decrypted_text or len(decrypted_text) <= 50:
                return None
            if 'decrypt-func-not-loaded' in decrypted_text:
                return None

            # Check for garbled text: if >30% of chars are rare Unicode, skip
            rare_count = sum(1 for c in decrypted_text if ord(c) > 0x4DB5)
            if rare_count / max(len(decrypted_text), 1) >= 0.3:
                return None

            questions = [{"type": "quiz_full", "text": decrypted_text}]
            solve_text_fn, _ = solver._get_ai_solver()
            answers = solve_text_fn(questions, solver.name, "")
            q_count = count_questions_in_text(decrypted_text)

            if answers:
                return {"answers": answers, "q_count": q_count, "mode": "text", "q_infos": None}
            return None
        except Exception as e:
            log(f"[{self.name}] WARN — {e}")
            return None


class V2ScreenshotStrategy(SolvingStrategy):
    """Tier 2: Screenshot each .TiMu container via element.screenshot().

    Uses a single JS pass to find .TiMu containers, screenshot each one,
    extract per-question metadata (qid, qtype, img count), then batch-solve
    via the configured AI image solver.
    """

    @property
    def name(self) -> str:
        return "V2Screenshot"

    @property
    def tier(self) -> int:
        return 2

    def try_solve(self, solver) -> dict | None:
        from ...logging_setup import log
        import os

        q_infos = None
        try:
            q_infos = solver._capture_question_screenshots_v2()
            if not q_infos:
                return None

            q_count = len(q_infos)
            answers = solver._solve_batched(q_infos, batch_size=5, section_key="")

            if answers:
                return {"answers": answers, "q_count": q_count, "mode": "image", "q_infos": q_infos}
            return None
        except Exception as e:
            log(f"[{self.name}] WARN — {e}")
            return None
        finally:
            # Always clean up V2 screenshots to prevent disk accumulation
            if q_infos:
                for qi in q_infos:
                    p = qi.get("path", "")
                    if p and os.path.exists(p):
                        try:
                            os.unlink(p)
                        except Exception:
                            pass


class V1ScreenshotStrategy(SolvingStrategy):
    """Tier 3: Clip-based per-question screenshots (y-coordinate arithmetic).

    Uses .newZy_TItle / .Zy_TItle elements as question boundaries, then
    screenshots each question with a clip rect. More fragile than V2 but
    works on older quiz layouts.
    """

    @property
    def name(self) -> str:
        return "V1Screenshot"

    @property
    def tier(self) -> int:
        return 3

    def try_solve(self, solver) -> dict | None:
        import os

        question_images = solver._capture_question_screenshots()

        if not question_images:
            return None

        q_count = len(question_images)
        _, solve_image_fn = solver._get_ai_solver()

        try:
            answers = solve_image_fn(question_images, solver.name, "")
            if answers:
                return {"answers": answers, "q_count": q_count, "mode": "image", "q_infos": None}
            return None
        except Exception as e:
            log(f"[{self.name}] WARN — {e}")
            return None
        finally:
            for p in question_images:
                try:
                    os.unlink(p)
                except Exception:
                    pass


class FullPageScreenshotStrategy(SolvingStrategy):
    """Tier 4: Single full-page screenshot of the quiz iframe body.

    Last image-based resort — one large screenshot containing all questions.
    Less reliable than per-question screenshots (AI may miss question boundaries)
    but works when DOM selectors fail entirely.
    """

    @property
    def name(self) -> str:
        return "FullPageScreenshot"

    @property
    def tier(self) -> int:
        return 4

    def try_solve(self, solver) -> dict | None:
        import os

        image_path = solver._capture_quiz_screenshot()
        if not image_path:
            return None

        _, solve_image_fn = solver._get_ai_solver()

        try:
            answers = solve_image_fn([image_path], solver.name, "")
            if answers:
                return {"answers": answers, "q_count": 0, "mode": "image", "q_infos": None}
            return None
        except Exception as e:
            log(f"[{self.name}] WARN — {e}")
            return None
        finally:
            try:
                os.unlink(image_path)
            except Exception:
                pass


class SnapshotTextStrategy(SolvingStrategy):
    """Tier 5: YAML snapshot text extraction (last resort).

    Takes a Playwright accessibility snapshot, strips structural noise,
    extracts question text, and sends it to the text AI solver.
    """

    @property
    def name(self) -> str:
        return "SnapshotText"

    @property
    def tier(self) -> int:
        return 5

    def try_solve(self, solver) -> dict | None:
        from ...browser.engine import pw_snapshot
        from ..quiz.extractor import extract_questions_from_snapshot, count_questions_in_snapshot

        snap = pw_snapshot()

        # Check for already-completed markers
        if "暂无" in snap or "已完成" in snap:
            return {"answers": [], "q_count": 0, "mode": "text", "q_infos": None,
                    "already_done": True}

        questions = extract_questions_from_snapshot(snap)
        q_count = count_questions_in_snapshot(snap)
        solve_text_fn, _ = solver._get_ai_solver()

        try:
            answers = solve_text_fn(questions, solver.name, "")
            if answers:
                return {"answers": answers, "q_count": q_count, "mode": "text", "q_infos": None}
            return None
        except Exception as e:
            log(f"[{self.name}] WARN — {e}")
            return None


# Ordered strategy chain (best to worst)
STRATEGY_CHAIN = [
    FontDecryptTextStrategy(),
    V2ScreenshotStrategy(),
    V1ScreenshotStrategy(),
    FullPageScreenshotStrategy(),
    SnapshotTextStrategy(),
]
