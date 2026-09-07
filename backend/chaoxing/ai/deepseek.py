"""
DeepSeek API Solver — deepseek-v4-flash-vision-exp backend.

Thin shell over the provider-agnostic pipeline in chaoxing.ai.doubao:
prompts, image encoding, answer parsing, batching and retry all live there;
only the provider id differs (credentials file, key var, base URL — see
_PROVIDERS in doubao.py).

Endpoint: https://api.deepseek.com (OpenAI-compatible)
Model: deepseek-v4-flash-vision-exp (text + vision), configured in
passwords/deepseek.txt
SDK: openai >= 1.0.0
"""

import os
import time

from ._base import AISolver
from ..logging_setup import log

from .doubao import (
    _build_text_prompt,
    _build_image_prompt,
    _encode_image_to_base64,
    _call_chat_completion,
    _parse_quiz_answer,
)

PROVIDER_ID = "deepseek-api"


def deepseek_solve_quiz(questions_text: str, course_name: str,
                        section_name: str, timeout: int = 180) -> list[dict]:
    """Solve quiz questions via DeepSeek (text-only)."""
    import re
    prompt = _build_text_prompt(questions_text, course_name, section_name)

    q_markers = re.findall(r'(?:^|\n)\s*(\d+)[\.、)]', questions_text)
    expected_count = len(set(q_markers)) if q_markers else 0

    log(
        f"[DeepSeek] Solving quiz: {course_name} / {section_name} "
        f"(expected ~{expected_count} questions, text mode)"
    )

    start = time.time()
    messages = [{"role": "user", "content": prompt}]
    raw_answer = _call_chat_completion(
        messages, timeout=timeout, provider=PROVIDER_ID)
    elapsed = time.time() - start

    log(f"[DeepSeek] Text solve completed in {elapsed:.1f}s")

    answers = _parse_quiz_answer(raw_answer)
    log(f"[DeepSeek] Parsed {len(answers)} answers")

    return answers


def deepseek_solve_quiz_image(image_paths: list[str], course_name: str,
                              section_name: str,
                              timeout: int = 180) -> list[dict]:
    """Solve quiz from screenshots via DeepSeek (multimodal vision)."""
    for p in image_paths:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Quiz screenshot not found: {p}")

    q_count = len(image_paths)
    prompt = _build_image_prompt(q_count, course_name, section_name)

    content = [{"type": "text", "text": prompt}]

    for i, path in enumerate(image_paths):
        b64_data = _encode_image_to_base64(path)
        file_size_kb = os.path.getsize(path) / 1024
        log(
            f"[DeepSeek] Encoding image {i+1}/{q_count}: "
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
        f"[DeepSeek] Solving quiz: {course_name} / {section_name} "
        f"({q_count} images, multimodal mode)"
    )

    start = time.time()
    messages = [{"role": "user", "content": content}]
    raw_answer = _call_chat_completion(
        messages, timeout=timeout, provider=PROVIDER_ID)
    elapsed = time.time() - start

    log(f"[DeepSeek] Image solve completed in {elapsed:.1f}s")

    answers = _parse_quiz_answer(raw_answer)
    log(f"[DeepSeek] Parsed {len(answers)} answers")

    return answers


def deepseek_ask_image(image_paths: list[str], prompt: str,
                       timeout: int = 180) -> str:
    """Send images with an arbitrary grading prompt; raw text back."""
    for p in image_paths:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Image not found: {p}")

    content = [{"type": "text", "text": prompt}]

    for i, path in enumerate(image_paths):
        b64_data = _encode_image_to_base64(path)
        log(
            f"[DeepSeek] Encoding grading image {i+1}/{len(image_paths)}: "
            f"{os.path.basename(path)}"
        )
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{b64_data}"
            }
        })

    start = time.time()
    messages = [{"role": "user", "content": content}]
    raw = _call_chat_completion(
        messages, timeout=timeout, provider=PROVIDER_ID)
    elapsed = time.time() - start

    log(f"[DeepSeek] Grading completed in {elapsed:.1f}s")
    return raw


class DeepSeekAPISolver(AISolver):
    """AISolver implementation for the DeepSeek API provider."""

    @property
    def provider_name(self) -> str:
        return "deepseek-api"

    def solve_quiz_text(self, questions: list[dict], course_name: str,
                        section_name: str) -> list[dict]:
        from .prompts import format_quiz_text_prompt
        questions_text = format_quiz_text_prompt(questions, course_name, section_name)
        return deepseek_solve_quiz(questions_text, course_name, section_name)

    def solve_quiz_image(self, image_paths: list[str], course_name: str,
                         section_name: str) -> list[dict]:
        return deepseek_solve_quiz_image(
            image_paths, course_name, section_name)

    def grade_quiz_image(self, image_paths: list[str], prompt: str,
                         timeout: int = 180) -> str:
        return deepseek_ask_image(image_paths, prompt, timeout)


def query_deepseek_balance() -> dict:
    """Query the DeepSeek account balance (GET /user/balance, free of charge).

    Uses the OpenAI SDK's raw GET (the endpoint is not part of the chat API
    surface), so no extra dependency beyond `openai` is needed.

    Returns dict shaped like the Doubao billing result so the frontend's
    Balance type maps 1:1.
    """
    import httpx
    from .doubao import _load_credentials, _PROVIDERS

    creds = _load_credentials("deepseek-api")
    base = _PROVIDERS["deepseek-api"]["base_url"]
    resp = httpx.get(f"{base}/user/balance",
                     headers={"Authorization": f"Bearer {creds['api_key']}"},
                     timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if not data.get("is_available", False):
        raise RuntimeError("DeepSeek 账户当前不可用（is_available=false）。")

    infos = data.get("balance_infos") or []
    cny = next((b for b in infos if b.get("currency") == "CNY"), infos[0] if infos else None)
    if cny is None:
        raise RuntimeError("DeepSeek 余额响应中没有 balance_infos。")

    return {
        "accountId": "deepseek",
        "availableBalance": cny.get("total_balance", "0"),
        "cashBalance": cny.get("topped_up_balance", "0"),
        "creditLimit": "0.00",
        "grantedBalance": cny.get("granted_balance", "0"),
        "arrearsBalance": "0.00",
        "freezeAmount": "0.00",
        "currency": cny.get("currency", "CNY"),
    }
