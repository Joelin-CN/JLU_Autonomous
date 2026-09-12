"""
Consolidated AI prompt templates for quiz solving and grading.

All text prompts used across the quiz-solving pipeline live here,
making it easy to tune prompt quality without hunting through
scattered code.
"""


def format_quiz_text_prompt(questions: list[dict], course_name: str,
                             section_name: str) -> str:
    """Format structured questions into a text prompt for AI solving.

    Args:
        questions: List of {index, question, options} dicts.
        course_name: e.g. "概率论与数理统计".
        section_name: e.g. "章节测试1".

    Returns:
        Prompt string ready for AI text input.
    """
    lines = [
        f"课程：{course_name}",
        f"章节：{section_name}",
        "",
        "请回答以下题目，每题只返回答案字母（如 A、B、C、D 或判断题 对/错）：",
        "",
    ]

    for q in questions:
        idx = q.get("index", "?")
        question_text = q.get("question", "")
        options = q.get("options", [])

        lines.append(f"第{idx}题：{question_text}")
        for opt in options:
            lines.append(f"  {opt}")
        lines.append("")

    lines.append("请以 JSON 数组格式返回结果：")
    lines.append('[{"index": 1, "answer": "A"}, {"index": 2, "answer": "B"}, ...]')
    lines.append("")
    lines.append("只返回 JSON 数组，不要其他内容。")

    return "\n".join(lines)


def format_quiz_image_prompt(course_name: str, section_name: str,
                              question_count: int = 0) -> str:
    """Format a prompt for AI image-based quiz solving.

    Args:
        course_name: Course name for context.
        section_name: Section name for context.
        question_count: Number of question screenshots being sent.

    Returns:
        Prompt string for image-based AI input.
    """
    count_hint = f"共{question_count}道题，" if question_count > 0 else ""
    return (
        f"课程：{course_name}\n"
        f"章节：{section_name}\n\n"
        f"请回答以下{count_hint}题目。每题只返回答案字母"
        f"（如 A、B、C、D 或判断题 对/错）：\n\n"
        f"请以 JSON 数组格式返回结果：\n"
        f'[{{"index": 1, "answer": "A"}}, {{"index": 2, "answer": "B"}}, ...]\n\n'
        f"只返回 JSON 数组，不要其他内容。"
    )


def format_grading_prompt() -> str:
    """Return the standard grading prompt for filled quiz screenshots.

    The grader sends this along with screenshots of submitted answers
    to the AI for correctness analysis.
    """
    return (
        "请仔细查看以下已提交的答题截图，判断每题答案是否正确。\n"
        "对于每道题，请指出：\n"
        "1. 题目编号\n"
        "2. 填写的答案\n"
        "3. 是否正确（✓ 或 ✗）\n"
        "4. 如果错误，请给出正确答案\n\n"
        "请以 JSON 数组格式返回结果：\n"
        '[{"index": 1, "filled_answer": "A", "correct": true}, ...]'
    )


def format_captcha_prompt() -> str:
    """Return the prompt for CAPTCHA image OCR via AI."""
    return "请识别图片中的验证码文字。只返回验证码文字本身，不要其他任何内容。"
