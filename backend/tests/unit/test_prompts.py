"""Tests for AI prompt formatting functions."""

from chaoxing.ai.prompts import (
    format_quiz_text_prompt,
    format_quiz_image_prompt,
    format_grading_prompt,
    format_captcha_prompt,
)


class TestFormatQuizTextPrompt:
    """Test format_quiz_text_prompt with structured question data."""

    def test_single_question(self):
        """Should format a single question with options."""
        questions = [
            {
                "index": 1,
                "question": "What is the capital of France?",
                "options": ["A. Paris", "B. London", "C. Berlin", "D. Madrid"],
            }
        ]
        prompt = format_quiz_text_prompt(questions, "Geography", "Chapter 1 Quiz")

        assert "Geography" in prompt
        assert "Chapter 1 Quiz" in prompt
        assert "第1题" in prompt
        assert "Paris" in prompt
        assert "London" in prompt
        assert "JSON" in prompt or "json" in prompt.lower()

    def test_multiple_questions(self):
        """Should format multiple questions correctly."""
        questions = [
            {"index": 1, "question": "Q1?", "options": ["A. a", "B. b"]},
            {"index": 2, "question": "Q2?", "options": ["A. c", "B. d"]},
            {"index": 3, "question": "Q3?", "options": ["A. e", "B. f"]},
        ]
        prompt = format_quiz_text_prompt(questions, "Math", "Test 2")

        assert "第1题" in prompt
        assert "第2题" in prompt
        assert "第3题" in prompt
        assert "Q1?" in prompt
        assert "Q3?" in prompt

    def test_empty_options(self):
        """Should handle questions with no options (essay/fill-in-the-blank)."""
        questions = [
            {"index": 1, "question": "Explain the meaning of life.", "options": []}
        ]
        prompt = format_quiz_text_prompt(questions, "Philosophy", "Final")

        assert "第1题" in prompt
        assert "Explain the meaning of life" in prompt

    def test_missing_index_defaults(self):
        """Should handle missing index gracefully."""
        questions = [
            {"question": "Who am I?", "options": ["A. Me", "B. You"]}
        ]
        prompt = format_quiz_text_prompt(questions, "Psychology", "Self")

        # Missing index shows "?" as placeholder
        assert "第?" in prompt

    def test_course_and_section_in_output(self):
        """Course and section names should appear in the prompt."""
        prompt = format_quiz_text_prompt([], "概率论", "章节测试1")
        assert "概率论" in prompt
        assert "章节测试1" in prompt


class TestFormatQuizImagePrompt:
    """Test format_quiz_image_prompt with course/section names."""

    def test_basic_image_prompt(self):
        """Should include course name and section name."""
        prompt = format_quiz_image_prompt("线性代数", "第三章测试", question_count=5)
        assert "线性代数" in prompt
        assert "第三章测试" in prompt
        assert "共5道题" in prompt
        assert "JSON" in prompt or "json" in prompt.lower()

    def test_zero_question_count(self):
        """Should handle zero question count (count hint omitted)."""
        prompt = format_quiz_image_prompt("Physics", "Quiz", question_count=0)
        assert "Physics" in prompt
        assert "Quiz" in prompt
        # No "共0道题" - count hint should be omitted when 0
        assert "共0道" not in prompt


class TestFormatGradingPrompt:
    """Test format_grading_prompt returns a usable grading prompt."""

    def test_returns_non_empty_string(self):
        """Should return a non-empty prompt string."""
        prompt = format_grading_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "答题截图" in prompt or "screenshot" in prompt.lower()

    def test_includes_json_format_instructions(self):
        """Should include JSON output format instructions."""
        prompt = format_grading_prompt()
        assert "JSON" in prompt or "json" in prompt.lower()
        assert "filled_answer" in prompt or "correct" in prompt


class TestFormatCaptchaPrompt:
    """Test format_captcha_prompt returns a CAPTCHA OCR prompt."""

    def test_returns_non_empty_string(self):
        """Should return a non-empty prompt string."""
        prompt = format_captcha_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_mentions_verification_code(self):
        """Should reference verification code / CAPTCHA in the prompt."""
        prompt = format_captcha_prompt()
        assert "验证码" in prompt or "captcha" in prompt.lower()
