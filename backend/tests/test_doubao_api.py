"""
Test Doubao API Quiz Solving
=============================
Isolated test of the doubao_api.py module before integrating into
the main quiz solver pipeline.

Tests:
  1. Credential loading
  2. Text quiz solving (3 sample questions)
  3. Image quiz solving (generated test image)
  4. JSON answer parsing (various formats)

Usage:
    conda run -n base python tests/test_doubao_api.py
"""
import sys
import time
import json
import os
import tempfile
from pathlib import Path

# Ensure scripts/ is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from doubao_api import (
    doubao_solve_quiz,
    doubao_solve_quiz_image,
    doubao_ask_image,
    _load_credentials,
    _parse_quiz_answer,
    _normalize_answer_keys,
    _encode_image_to_base64,
    _build_text_prompt,
    _build_image_prompt,
)

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}" + (f" -- {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f" -- {detail}" if detail else ""))


# ── Test 1: Credential Loading ────────────────────────────────

def test_load_credentials():
    print("\n-- Test 1: Credential Loading --")
    creds = _load_credentials()
    check("api_key starts with 'ark-'", creds["api_key"].startswith("ark-"), creds["api_key"][:20] + "...")
    check("model starts with 'ep-'", creds["model"].startswith("ep-"), creds["model"])


# ── Test 2: Text Quiz Solving ─────────────────────────────────

SAMPLE_QUESTIONS = """第1题 [单选题] 设随机变量X服从正态分布N(0,1)，则P(X>0)等于多少？
A. 0
B. 0.5
C. 1
D. 0.25

第2题 [多选题] 以下哪些是概率的合法取值？
A. 0
B. 0.5
C. 1
D. 1.5

第3题 [判断题] 若事件A与B互斥，则P(A∪B)=P(A)+P(B)。
正确
错误"""


def test_text_quiz_solving():
    print("\n── Test 2: Text Quiz Solving ──")
    print("  Sending 3 sample questions to Doubao API...")

    start = time.time()
    try:
        answers = doubao_solve_quiz(
            SAMPLE_QUESTIONS,
            "概率论与数理统计",
            "章节测试(API测试)"
        )
        elapsed = time.time() - start
        print(f"  Response time: {elapsed:.1f}s")

        check("returns non-empty list", len(answers) > 0, f"got {len(answers)} answers")
        check("returns 3 answers", len(answers) == 3, json.dumps(answers, ensure_ascii=False)[:200])

        if len(answers) >= 3:
            a1 = answers[0]
            check("Q1 has 'index' key", "index" in a1)
            check("Q1 has 'answer' key", "answer" in a1)
            print(f"  Q1 answer: {a1.get('answer')}")
            print(f"  Q2 answer: {answers[1].get('answer')}")
            print(f"  Q3 answer: {answers[2].get('answer')}")

    except Exception as e:
        check(f"no exception: {type(e).__name__}", False, str(e)[:200])


# ── Test 3: Image Quiz Solving ────────────────────────────────

def _create_test_image() -> str:
    """Generate a simple test PNG with Chinese text representing a quiz question."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (800, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Try to use a CJK font
    font = None
    font_paths = [
        "C:/Windows/Fonts/msyh.ttc",       # Microsoft YaHei
        "C:/Windows/Fonts/simsun.ttc",      # SimSun
        "C:/Windows/Fonts/simhei.ttf",      # SimHei
        "C:/Windows/Fonts/STSONG.TTF",      # 华文宋体
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 20)
                break
            except Exception:
                pass

    if font is None:
        font = ImageFont.load_default()

    draw.text((20, 20), "第1题 [单选题] 1+1等于多少？", fill=(0, 0, 0), font=font)
    draw.text((40, 60), "A. 0", fill=(0, 0, 0), font=font)
    draw.text((40, 90), "B. 1", fill=(0, 0, 0), font=font)
    draw.text((40, 120), "C. 2", fill=(0, 0, 0), font=font)
    draw.text((40, 150), "D. 3", fill=(0, 0, 0), font=font)
    draw.text((20, 200), "第2题 [判断题] 地球是圆的。", fill=(0, 0, 0), font=font)
    draw.text((40, 230), "正确", fill=(0, 0, 0), font=font)
    draw.text((40, 260), "错误", fill=(0, 0, 0), font=font)

    path = os.path.join(tempfile.gettempdir(), "_doubao_test_quiz.png")
    img.save(path, "PNG")
    return path


def test_image_quiz_solving():
    print("\n── Test 3: Image Quiz Solving ──")
    print("  Generating test image...")
    img_path = _create_test_image()
    print(f"  Test image: {img_path} ({os.path.getsize(img_path)/1024:.1f} KB)")

    check("test image exists", os.path.exists(img_path))

    print("  Sending image to Doubao API (multimodal)...")
    start = time.time()
    try:
        answers = doubao_solve_quiz_image(
            [img_path],
            "概率论与数理统计",
            "章节测试(API图片测试)"
        )
        elapsed = time.time() - start
        print(f"  Response time: {elapsed:.1f}s")

        check("returns non-empty list", len(answers) > 0, f"got {len(answers)} answers")
        if answers:
            print(f"  Answers: {json.dumps(answers, ensure_ascii=False)[:300]}")

    except Exception as e:
        check(f"no exception: {type(e).__name__}", False, str(e)[:300])
    finally:
        try:
            os.unlink(img_path)
        except Exception:
            pass


# ── Test 4: JSON Parsing ──────────────────────────────────────

def test_json_parsing():
    print("\n── Test 4: JSON Answer Parsing ──")

    # Clean JSON
    clean = '[{"index":1,"answer":"A"},{"index":2,"answer":["B","C"]}]'
    result = _parse_quiz_answer(clean)
    check("parses clean JSON", len(result) == 2, str(result))
    if len(result) >= 2:
        check("Q1 answer is 'A'", result[0]["answer"] == "A")
        check("Q2 answer is ['B','C']", result[1]["answer"] == ["B", "C"])

    # Markdown-wrapped JSON
    md_wrapped = '```json\n[{"index":1,"answer":"正确"}]\n```'
    result = _parse_quiz_answer(md_wrapped)
    check("parses markdown-wrapped JSON", len(result) == 1 and result[0]["answer"] == "正确")

    # JSON with extra text before and after
    with_extra = '好的，以下是答案：\n[{"index":1,"answer":"D"}]\n希望对你有帮助！'
    result = _parse_quiz_answer(with_extra)
    check("parses JSON with extra text", len(result) == 1 and result[0]["answer"] == "D",
          str(result))

    # Alternative key names
    alt_keys = '[{"id":1,"ans":"A"},{"question_num":2,"result":"B"}]'
    result = _parse_quiz_answer(alt_keys)
    check("normalizes alternative keys", len(result) == 2, str(result))
    if len(result) >= 2:
        check("id→index, ans→answer", result[0].get("index") == 1 and result[0].get("answer") == "A")
        check("question_num→index, result→answer",
              result[1].get("index") == 2 and result[1].get("answer") == "B")

    # Empty/invalid input
    empty = _parse_quiz_answer("这不是JSON，纯文本回答")
    check("returns empty list for non-JSON", empty == [], str(empty)[:100])

    # Nested arrays in answer
    nested = '[{"index":1,"answer":["A","C","D"]},{"index":2,"answer":"正确"}]'
    result = _parse_quiz_answer(nested)
    check("parses nested array answers", len(result) == 2, str(result))
    if len(result) >= 1:
        check("nested answer preserved", result[0]["answer"] == ["A", "C", "D"])


# ── Test 5: Base64 Encoding ───────────────────────────────────

def test_base64_encoding():
    print("\n── Test 5: Base64 Image Encoding ──")
    img_path = _create_test_image()
    try:
        b64 = _encode_image_to_base64(img_path)
        check("returns non-empty string", len(b64) > 0)
        check("is valid base64", len(b64) % 4 == 0, f"length: {len(b64)}")
        # Verify it decodes back
        import base64
        decoded = base64.b64decode(b64)
        check("decodes to original size",
              len(decoded) == os.path.getsize(img_path),
              f"{len(decoded)} vs {os.path.getsize(img_path)}")
    finally:
        try:
            os.unlink(img_path)
        except Exception:
            pass


# ── Test 6: Prompt Building ───────────────────────────────────

def test_prompt_building():
    print("\n── Test 6: Prompt Building ──")
    text_prompt = _build_text_prompt("1. 什么是概率？\nA. 随机事件\nB. 确定事件", "测试课", "第一章测试")
    check("text prompt contains course name", "测试课" in text_prompt)
    check("text prompt contains section name", "第一章测试" in text_prompt)
    check("text prompt contains JSON format", "JSON" in text_prompt)

    img_prompt = _build_image_prompt(3, "物理", "第二章测试")
    check("image prompt mentions 3 questions", "3 道题" in img_prompt)
    check("image prompt has mapping", "第1张图片 = 第1题" in img_prompt)
    check("image prompt has mapping", "第3张图片 = 第3题" in img_prompt)


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("DOUBAO API — ISOLATED TEST SUITE")
    print("=" * 60)

    test_load_credentials()
    test_json_parsing()
    test_base64_encoding()
    test_prompt_building()

    # Live API tests (require network)
    print("\n" + "=" * 60)
    print("LIVE API TESTS (requires network)")
    print("=" * 60)

    test_text_quiz_solving()
    test_image_quiz_solving()

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
    print("=" * 60)

    if FAIL > 0:
        print("\n⚠ SOME TESTS FAILED — check output above for details.")
        sys.exit(1)
    else:
        print("\n✓ ALL TESTS PASSED")
