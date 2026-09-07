"""
AI solver factory — selects and instantiates the configured AI backend.

Uses chaoxing_config.json → ai.provider to decide which solver to use.
Supports runtime switching without code changes.
"""

from ..config import cfg, get_config
from ..logging_setup import log
from ..exceptions import ConfigError


def get_ai_solver():
    """Factory: Return the configured AISolver instance.

    Doubao API is the sole AI backend. Results are cached after first
    call for the current process lifetime.

    Returns:
        DoubaoAPISolver instance.

    Raises:
        ConfigError: If the configured provider is unknown.
    """
    provider = cfg("ai.provider", "doubao-api")

    if provider == "doubao-api":
        from .doubao import DoubaoAPISolver
        return DoubaoAPISolver()

    if provider == "deepseek-api":
        from .deepseek import DeepSeekAPISolver
        return DeepSeekAPISolver()

    else:
        raise ConfigError(
            f"Unknown AI provider: '{provider}'. "
            f"Valid options: 'doubao-api', 'deepseek-api'. "
            f"Check chaoxing_config.json → ai.provider."
        )


def get_ai_grader():
    """Factory: Return an AISolver configured for grading (same as solver).

    In the current architecture, grading uses the same backend as solving.
    This is a convenience alias for clarity in the grader module.
    """
    return get_ai_solver()


# ── Convenience functions (backward compat with original utils.py) ─

def ai_solve_quiz(questions: list[dict], course_name: str,
                  section_name: str) -> list[dict]:
    """Solve quiz from text. Backward-compatible wrapper."""
    solver = get_ai_solver()
    return solver.solve_quiz_text(questions, course_name, section_name)


def ai_solve_quiz_image(image_paths: list[str], course_name: str,
                         section_name: str) -> list[dict]:
    """Solve quiz from images. Backward-compatible wrapper."""
    solver = get_ai_solver()
    return solver.solve_quiz_image(image_paths, course_name, section_name)


def ai_grade_quiz_image(image_paths: list[str], prompt: str = "",
                         timeout: int = 180) -> str:
    """Grade filled quiz screenshots. Backward-compatible wrapper."""
    solver = get_ai_grader()
    return solver.grade_quiz_image(image_paths, prompt, timeout)
