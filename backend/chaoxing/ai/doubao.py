"""
Doubao (豆包) API Solver — Volcano Ark / 火山方舟 backend.

Implements AISolver via the Doubao model endpoint using the OpenAI SDK.
Fast, stateless HTTP API — the default AI provider.

Endpoint: https://ark.cn-beijing.volces.com/api/v3
Model: endpoint ID (ep-...) configured in passwords/doubao.txt
SDK: openai >= 1.0.0

This is the CANONICAL implementation. All real logic lives here.
scripts/doubao_api.py is a backward-compatible re-export shim.
"""

import sys
import time
import re
import json
import os
import base64
from typing import Optional

from ._base import AISolver
from ..exceptions import AIBackendError
from ..logging_setup import log
from ..constants import CREDS_DIR

CREDS_FILE = CREDS_DIR / "doubao.txt"

# OpenAI-compatible providers. Providers differ ONLY in credentials file,
# key variable name, and base URL — all solving/grading/batching logic
# below is provider-agnostic and selected per call.
_PROVIDERS = {
    "doubao-api": {
        "creds_file": CREDS_DIR / "doubao.txt",
        "key_var": "ARK_API_KEY",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "label": "Doubao",
    },
    "deepseek-api": {
        "creds_file": CREDS_DIR / "deepseek.txt",
        "key_var": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
        "label": "DeepSeek",
    },
}


# ══════════════════════════════════════════════════════════════════
#  Credentials
# ══════════════════════════════════════════════════════════════════

def _load_credentials(provider: str = "doubao-api") -> dict:
    """Parse the provider API key and model from passwords/<name>.txt.

    File format:
        export <KEY_VAR>="sk-..."
        model="..."

    Returns dict with keys: api_key, model.
    """
    spec = _PROVIDERS.get(provider)
    if spec is None:
        raise ValueError(f"Unknown AI provider: {provider}")
    creds_file = spec["creds_file"]
    key_var = spec["key_var"]

    if not creds_file.exists():
        raise FileNotFoundError(
            f"{provider} credentials not found: {creds_file}\n"
            f"Create data/passwords/{creds_file.name} with {key_var} and model."
        )

    content = creds_file.read_text(encoding="utf-8")

    api_key = ""
    model = ""

    # Extract the key (handle both export shell syntax and plain env syntax)
    key_match = re.search(rf'{key_var}\s*=\s*"([^"]+)"', content)
    if not key_match:
        key_match = re.search(rf'{key_var}\s*=\s*(\S+)', content)
    if key_match:
        api_key = key_match.group(1).strip()

    # Extract model
    model_match = re.search(r'model\s*=\s*"([^"]+)"', content)
    if not model_match:
        model_match = re.search(r'model\s*=\s*(\S+)', content)
    if model_match:
        model = model_match.group(1).strip()

    if not api_key:
        raise ValueError(
            f"Could not parse {key_var} from {creds_file}. "
            f"Expected format: {key_var}=\"sk-...\""
        )
    if not model:
        raise ValueError(
            f"Could not parse model from {creds_file}. "
            f"Expected format: model=\"...\""
        )

    return {"api_key": api_key, "model": model}


# ══════════════════════════════════════════════════════════════════
#  Client Factory
# ══════════════════════════════════════════════════════════════════

def _create_client(api_key: str, timeout: int = 180,
                   provider: str = "doubao-api"):
    """Create an OpenAI-compatible client for the given provider.

    The SDK auto-appends /chat/completions — do NOT include it in base_url.

    Args:
        api_key: API key from the provider's credentials file.
        timeout: Request timeout in seconds.
        provider: Provider id from _PROVIDERS.
    """
    from openai import OpenAI

    return OpenAI(
        base_url=_PROVIDERS[provider]["base_url"],
        api_key=api_key,
        timeout=timeout,
        max_retries=0,  # We handle retries ourselves for better logging
    )


# ══════════════════════════════════════════════════════════════════
#  Image Encoding
# ══════════════════════════════════════════════════════════════════

def _encode_image_to_base64(image_path: str) -> str:
    """Read a local PNG/JPG file and return its base64 string (no data URI prefix)."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ══════════════════════════════════════════════════════════════════
#  Prompt Builders
# ══════════════════════════════════════════════════════════════════

def _build_text_prompt(questions_text: str, course_name: str,
                       section_name: str) -> str:
    """Build the quiz-solving prompt for text-only mode."""
    q_markers = re.findall(r'(?:^|\n)\s*(\d+)[\.、)]', questions_text)
    expected_count = len(set(q_markers)) if q_markers else 0

    count_hint = ""
    if expected_count > 0:
        count_hint = f"\n共 {expected_count} 道题，请只返回 {expected_count} 个答案，不要多余答案。"

    return f"""你正在解答大学课程 "{course_name}" 中 "{section_name}" 的章节测试题。

请仔细阅读以下题目，给出每道题的正确答案。{count_hint}

将答案以JSON数组格式返回，每道题一个对象：
```json
[
  {{"index": 1, "answer": "A"}},
  {{"index": 2, "answer": ["A", "C"]}},
  {{"index": 3, "answer": "正确"}},
  {{"index": 4, "answer": "这里是简答题的文本答案"}}
]
```

规则：
- 单选题: answer 为选项字母字符串，如 "A"
- 多选题: answer 为选项字母数组，如 ["A", "B", "D"]
- 判断题: answer 为 "正确" 或 "错误"
- 简答题: answer 为完整的文本答案
- 填空题: answer 为填入的文本
- 只回答题目中实际出现的题号，不要编造不存在的题目

题目内容：
{questions_text}

只返回JSON数组，不要其他文字。"""


def _build_image_prompt(image_count: int, course_name: str,
                        section_name: str) -> str:
    """Build the quiz-solving prompt for multimodal (image) mode."""
    q_count = image_count
    mapping_lines = "\n".join(
        f"- 第{i+1}张图片 = 第{i+1}题"
        for i in range(q_count)
    )

    return f"""你正在解答大学课程 "{course_name}" 中 "{section_name}" 的章节测试题。

共 {q_count} 道题，上传了 {q_count} 张图片，每张图片是一道完整的题目。图片编号对应题号：
{mapping_lines}

请按顺序给出每道题的正确答案。必须正好 {q_count} 个答案，不要多也不要少。

将答案以JSON数组格式返回：
```json
[
  {{"index": 1, "answer": "A"}},
  {{"index": 2, "answer": ["A", "C"]}},
  {{"index": 3, "answer": "正确"}},
  {{"index": 4, "answer": "这里是简答题的文本答案"}}
]
```

规则：
- 单选题: answer 为选项字母字符串，如 "A"
- 多选题: answer 为选项字母数组，如 ["A", "B", "D"]
- 判断题: answer 为 "正确" 或 "错误"
- 简答题/填空题: answer 为完整的文本答案
- 只返回 {q_count} 个答案，不要编造不存在的题目

只返回JSON数组，不要其他文字。"""


# ══════════════════════════════════════════════════════════════════
#  Chat Completion with Retry
# ══════════════════════════════════════════════════════════════════

def _call_chat_completion(
    messages: list[dict],
    timeout: int = 180,
    max_retries: int = 3,
    retry_base_delay: float = 2.0,
    provider: str = "doubao-api",
) -> str:
    """Call the configured provider with exponential-backoff retry.

    Args:
        messages: OpenAI-format message list.
        timeout: Request timeout in seconds.
        max_retries: Max retry attempts on transient errors.
        retry_base_delay: Base seconds for exponential backoff (2s -> 4s -> 8s).

    Returns:
        Model's text response (content string).

    Raises:
        openai.AuthenticationError, openai.BadRequestError (non-retryable).
        RuntimeError on final retry exhaustion.
    """
    from openai import (
        OpenAI,
        RateLimitError,
        APITimeoutError,
        APIConnectionError,
        InternalServerError,
        AuthenticationError,
        BadRequestError,
    )

    RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)

    creds = _load_credentials(provider)
    model = creds["model"]
    label = _PROVIDERS[provider]["label"]

    last_error = None

    # Use "with" so the httpx connection pool is properly closed after
    # each API call, preventing socket/fd accumulation and RAM growth.
    with _create_client(api_key=creds["api_key"], timeout=timeout,
                        provider=provider) as client:
        for attempt in range(1, max_retries + 2):  # 1 initial + N retries
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.1,
                )

                content = response.choices[0].message.content or ""

                # Log usage
                usage = response.usage
                if usage:
                    log(
                        f"[{label}] Tokens: prompt={usage.prompt_tokens}, "
                        f"completion={usage.completion_tokens}, "
                        f"total={usage.total_tokens}"
                    )

                return content

            except RETRYABLE as e:
                last_error = e
                if attempt <= max_retries:
                    delay = retry_base_delay * (2 ** (attempt - 1))
                    log(
                        f"[{label}] {type(e).__name__} on attempt {attempt}/{max_retries + 1}, "
                        f"retrying in {delay:.0f}s..."
                    )
                    time.sleep(delay)
                else:
                    log(
                        f"[{label}] {type(e).__name__} exhausted after "
                        f"{max_retries + 1} attempts: {e}"
                    )

            except (AuthenticationError, BadRequestError) as e:
                log(f"[Doubao] Fatal API error: {type(e).__name__}: {e}")
                raise AIBackendError(
                    f"Doubao API fatal error: {type(e).__name__}: {e}",
                    provider="doubao-api", retryable=False
                ) from e

            except TypeError:
                # Programming errors (wrong type passed, etc.) — don't retry
                raise

            except Exception as e:
                last_error = e
                if attempt <= max_retries:
                    delay = retry_base_delay * (2 ** (attempt - 1))
                    log(
                        f"[Doubao] Unexpected error on attempt {attempt}/{max_retries + 1}: "
                        f"{type(e).__name__}: {e}, retrying in {delay:.0f}s..."
                    )
                    time.sleep(delay)
                else:
                    log(f"[Doubao] Unexpected error exhausted: {type(e).__name__}: {e}")

    raise AIBackendError(
        f"Doubao API call failed after {max_retries + 1} attempts. "
        f"Last error: {type(last_error).__name__}: {last_error}",
        provider="doubao-api",
        retryable=True  # transient errors (rate limits, timeouts, connection) are retryable
    )


# ══════════════════════════════════════════════════════════════════
#  JSON Answer Parsing
# ══════════════════════════════════════════════════════════════════

def _normalize_answer_keys(answers: list[dict]) -> list[dict]:
    """Normalize AI response keys to canonical {index, answer} format."""
    INDEX_KEYS = ['index', 'id', 'question_num', 'question_number', 'q_index', 'no', 'num', 'n']
    ANSWER_KEYS = ['answer', 'answer_text', 'ans', 'result', 'value', 'text']

    normalized = []
    for item in answers:
        if not isinstance(item, dict):
            continue
        entry = {}

        # Normalize index
        for k in INDEX_KEYS:
            if k in item:
                entry['index'] = item[k]
                break
        if 'index' not in entry:
            entry['index'] = len(normalized) + 1

        # Normalize answer
        for k in ANSWER_KEYS:
            if k in item:
                entry['answer'] = item[k]
                break
        if 'answer' not in entry:
            # Last resort: grab first non-index value
            for k, v in item.items():
                if k not in INDEX_KEYS:
                    entry['answer'] = v
                    break

        if 'answer' in entry:
            normalized.append(entry)

    return normalized


def _parse_quiz_answer(text: str) -> list[dict]:
    """Extract JSON answer array from model response.

    Uses bracket-depth tracking for robust extraction even when
    answer values contain nested arrays (e.g. ["A", "C"]).

    Normalizes keys so downstream code always sees {index, answer}.
    """
    text = text.strip()

    # Remove markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1])
        elif len(lines) == 2:
            text = lines[1] if len(lines) > 1 else text

    def _try_normalize(candidate_text: str) -> list[dict] | None:
        """Try to parse and normalize JSON from text. Returns None on failure."""
        try:
            result = json.loads(candidate_text)
            if isinstance(result, list):
                return _normalize_answer_keys(result)
        except json.JSONDecodeError:
            pass
        return None

    # Try parsing the whole text first
    parsed = _try_normalize(text)
    if parsed:
        return parsed

    # Find JSON array with bracket-depth tracking
    start_idx = text.find('[')
    if start_idx >= 0:
        depth = 0
        for i in range(start_idx, len(text)):
            ch = text[i]
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    candidate = text[start_idx:i + 1]
                    parsed = _try_normalize(candidate)
                    if parsed:
                        return parsed
                    break

    # Legacy regex fallback
    match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if match:
        parsed = _try_normalize(match.group(0))
        if parsed:
            return parsed

    log(f"[Doubao] Could not parse JSON from answer. Raw: {text[:300]}")
    return []


# ══════════════════════════════════════════════════════════════════
#  Public API — Module-level functions
# ══════════════════════════════════════════════════════════════════

def doubao_solve_quiz(questions_text: str, course_name: str,
                      section_name: str, timeout: int = 180) -> list[dict]:
    """Send quiz questions to Doubao API (text-only) and parse the JSON answer.

    Args:
        questions_text: Formatted quiz text with questions and options.
        course_name: Course name for prompt context.
        section_name: Section name for prompt context.
        timeout: API timeout in seconds.

    Returns:
        list of {index, answer} dicts.
    """
    prompt = _build_text_prompt(questions_text, course_name, section_name)

    q_markers = re.findall(r'(?:^|\n)\s*(\d+)[\.、)]', questions_text)
    expected_count = len(set(q_markers)) if q_markers else 0

    log(
        f"[Doubao] Solving quiz: {course_name} / {section_name} "
        f"(expected ~{expected_count} questions, text mode)"
    )

    start = time.time()
    messages = [{"role": "user", "content": prompt}]
    raw_answer = _call_chat_completion(messages, timeout=timeout)
    elapsed = time.time() - start

    log(f"[Doubao] Text solve completed in {elapsed:.1f}s")

    answers = _parse_quiz_answer(raw_answer)
    log(f"[Doubao] Parsed {len(answers)} answers")

    return answers


def doubao_solve_quiz_image(image_paths: list[str], course_name: str,
                            section_name: str, timeout: int = 180) -> list[dict]:
    """Send quiz question screenshots to Doubao API (multimodal) and parse answers.

    All images are sent in a single API call using OpenAI vision format.
    Each image is base64-encoded and attached as an image_url content block.

    Args:
        image_paths: List of absolute paths to quiz question screenshot PNGs.
        course_name: Course name for prompt context.
        section_name: Section name for prompt context.
        timeout: API timeout in seconds.

    Returns:
        list of {index, answer} dicts.
    """
    for p in image_paths:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Quiz screenshot not found: {p}")

    q_count = len(image_paths)
    prompt = _build_image_prompt(q_count, course_name, section_name)

    # Build multimodal content array
    content = [{"type": "text", "text": prompt}]

    for i, path in enumerate(image_paths):
        b64_data = _encode_image_to_base64(path)
        file_size_kb = os.path.getsize(path) / 1024
        log(
            f"[Doubao] Encoding image {i+1}/{q_count}: "
            f"{os.path.basename(path)} ({file_size_kb:.1f} KB -> "
            f"{len(b64_data) / 1024:.1f} KB base64)"
        )
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{b64_data}"
            }
        })

    log(
        f"[Doubao] Solving quiz: {course_name} / {section_name} "
        f"({q_count} images, multimodal mode)"
    )

    start = time.time()
    messages = [{"role": "user", "content": content}]
    raw_answer = _call_chat_completion(messages, timeout=timeout)
    elapsed = time.time() - start

    log(f"[Doubao] Image solve completed in {elapsed:.1f}s")

    answers = _parse_quiz_answer(raw_answer)
    log(f"[Doubao] Parsed {len(answers)} answers")

    return answers


def doubao_ask_image(image_paths: list[str], prompt: str,
                     timeout: int = 180) -> str:
    """Send images with an arbitrary prompt to Doubao API (multimodal).

    Raw text return — no JSON parsing. Used by Phase C grading
    where the response format is grading-specific.

    Args:
        image_paths: List of absolute paths to PNG screenshots.
        prompt: The full prompt text (including grading instructions).
        timeout: API timeout in seconds.

    Returns:
        Raw model response text.
    """
    for p in image_paths:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Image not found: {p}")

    # Build multimodal content array
    content = [{"type": "text", "text": prompt}]

    for i, path in enumerate(image_paths):
        b64_data = _encode_image_to_base64(path)
        file_size_kb = os.path.getsize(path) / 1024
        log(
            f"[Doubao-Image] Encoding image {i+1}/{len(image_paths)}: "
            f"{os.path.basename(path)} ({file_size_kb:.1f} KB)"
        )
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{b64_data}"
            }
        })

    log(
        f"[Doubao-Image] Asking with {len(image_paths)} image(s), "
        f"prompt length: {len(prompt)} chars"
    )

    start = time.time()
    messages = [{"role": "user", "content": content}]
    raw_answer = _call_chat_completion(messages, timeout=timeout)
    elapsed = time.time() - start

    log(f"[Doubao-Image] Answer received in {elapsed:.1f}s ({len(raw_answer)} chars)")

    return raw_answer


# ══════════════════════════════════════════════════════════════════
#  AISolver implementation
# ══════════════════════════════════════════════════════════════════

class DoubaoAPISolver(AISolver):
    """Doubao API backend — fast, stateless, default provider."""

    @property
    def provider_name(self) -> str:
        return "doubao-api"

    def solve_quiz_text(self, questions: list[dict], course_name: str,
                        section_name: str) -> list[dict]:
        """Solve quiz from structured text via Doubao API."""
        from .prompts import format_quiz_text_prompt
        questions_text = format_quiz_text_prompt(questions, course_name, section_name)
        return doubao_solve_quiz(questions_text, course_name, section_name)

    def solve_quiz_image(self, image_paths: list[str], course_name: str,
                         section_name: str) -> list[dict]:
        """Solve quiz from screenshots via Doubao API (multimodal)."""
        return doubao_solve_quiz_image(image_paths, course_name, section_name)

    def grade_quiz_image(self, image_paths: list[str], prompt: str,
                         timeout: int = 180) -> str:
        """Grade filled quiz screenshots via Doubao API."""
        return doubao_ask_image(image_paths, prompt, timeout=timeout)


# ══════════════════════════════════════════════════════════════════
#  Legacy aliases (used by older scripts and tests)
# ══════════════════════════════════════════════════════════════════

ai_solve_quiz_doubao = doubao_solve_quiz
ai_solve_quiz_image_doubao = doubao_solve_quiz_image
