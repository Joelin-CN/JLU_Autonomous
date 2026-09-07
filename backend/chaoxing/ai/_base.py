"""
Abstract base class for pluggable AI quiz-solving backends.

All AI providers implement this interface, allowing the quiz solver
to work with any backend without code changes. Provider is configured via
chaoxing_config.json → ai.provider (currently only "doubao-api").
"""

from abc import ABC, abstractmethod


class AISolver(ABC):
    """Pluggable AI backend for quiz solving and grading.

    Concrete implementations:
        - DoubaoAPISolver (chaoxing.ai.doubao): HTTP API via OpenAI SDK, sole provider.
    """

    @abstractmethod
    def solve_quiz_text(self, questions: list[dict], course_name: str,
                        section_name: str) -> list[dict]:
        """Solve quiz questions from structured text.

        Args:
            questions: List of {index, question, options} dicts.
            course_name: Course name for context in the AI prompt.
            section_name: Section name for context.

        Returns:
            List of {index, answer} dicts (e.g., [{"index": 1, "answer": "A"}, ...]).
        """
        ...

    @abstractmethod
    def solve_quiz_image(self, image_paths: list[str], course_name: str,
                         section_name: str) -> list[dict]:
        """Solve quiz questions from screenshots (multimodal).

        Args:
            image_paths: List of absolute paths to question screenshot PNGs.
            course_name: Course name for context.
            section_name: Section name for context.

        Returns:
            List of {index, answer} dicts.
        """
        ...

    @abstractmethod
    def grade_quiz_image(self, image_paths: list[str], prompt: str,
                         timeout: int = 180) -> str:
        """Grade filled quiz screenshots — analyze correctness of submitted answers.

        Args:
            image_paths: Screenshots showing filled-in answers.
            prompt: Grading prompt with instructions.
            timeout: Max wait time in seconds.

        Returns:
            Raw model response string (parsed by the grader).
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name for logging (e.g., 'doubao-api')."""
        ...
