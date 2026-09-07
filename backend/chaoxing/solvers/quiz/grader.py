"""
Grade-only mode — capture filled-state screenshots, batch AI grading.

Phase C of the quiz pipeline: after filling answers but before submitting,
re-screenshot the .TiMu containers (showing selected radios/checkboxes),
then send to Doubao for independent re-evaluation.
"""

import json as _json
import math
import re
import time
import tempfile
import glob as _glob
import os

from ...constants import TMP_DIR
from ...logging_setup import log
from ...session import _get_active_session
from ...browser.viewport import ensure_chaoxing_viewport
from ...browser.js_runner import pw_run_code_file, pw_extract_result
from ...ai.router import ai_grade_quiz_image


def _parse_grade_answer(text: str) -> list[dict]:
    """Extract JSON grading array from Doubao response.

    Unlike _parse_quiz_answer, this PRESERVES all grading-specific fields:
    is_correct, correct_answer, selected, explanation.

    Uses bracket-depth tracking for robust extraction.
    Returns list of dicts with all original keys intact.
    """
    text = text.strip()

    # Remove markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1])
        elif len(lines) == 2:
            text = lines[1] if len(lines) > 1 else text

    # Try parsing the whole text first
    try:
        result = _json.loads(text)
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
            return result
    except _json.JSONDecodeError:
        pass

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
                    try:
                        result = _json.loads(candidate)
                        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
                            return result
                    except _json.JSONDecodeError:
                        pass
                    break

    # Legacy regex fallback
    match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if match:
        try:
            result = _json.loads(match.group(0))
            if isinstance(result, list):
                return result
        except _json.JSONDecodeError:
            pass

    return []


def _capture_filled_screenshots_v2() -> list[dict]:
    """Re-screenshot .TiMu containers AFTER filling answers.

    Same approach as _capture_question_screenshots_v2() but called after
    _fill_answers(). The screenshots now show selected radio buttons,
    checked checkboxes, green highlights -- visual proof of completion.

    Returns:
        list of {index, path, qid, qtype}, empty list on failure.
    """
    ensure_chaoxing_viewport(2048, 1152)

    script_dir = str(TMP_DIR)
    session = _get_active_session()
    sfx = f"_{session}" if session and session != "chaoxing-chrome" else ""

    # Clean stale filled screenshots
    for old in _glob.glob(os.path.join(script_dir, f'_quiz_filled_q*v2{sfx}.png')):
        try:
            os.unlink(old)
        except Exception:
            pass

    capture_js = r"""
    async (page) => {
        const candidates = page.frames().filter(f =>
            f !== page.mainFrame() &&
            (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
             f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
        );
        if (candidates.length === 0) return JSON.stringify({error: 'no-iframe'});

        let questions = [];

        for (const iframe of candidates) {
            try {
                const timuEls = iframe.locator('.TiMu');
                const count = await timuEls.count();
                if (count < 1) continue;

                for (let i = 0; i < count; i++) {
                    const el = timuEls.nth(i);
                    try {
                        await el.scrollIntoViewIfNeeded();
                        await page.waitForTimeout(200);

                        const path = Q_DIR + '/_quiz_filled_q' + (i + 1) + 'v2' + Q_SFX + '.png';
                        await el.screenshot({path});

                        // qid
                        let qid = '';
                        try {
                            const qidEl = el.locator('input[id^="answer"]');
                            const qidCount = await qidEl.count();
                            if (qidCount > 0) {
                                const rawId = await qidEl.first().getAttribute('id');
                                qid = (rawId || '').replace('answer', '');
                            }
                        } catch(e) {}

                        // Check answer value from hidden input
                        let answerValue = '';
                        try {
                            const qidEl = el.locator('input[id^="answer"]');
                            if (await qidEl.count() > 0) {
                                answerValue = (await qidEl.first().inputValue()) || '';
                            }
                        } catch(e) {}

                        // qtype
                        let qtype = 'unknown';
                        try {
                            const titleEl = el.locator('.newZy_TItle, .Zy_TItle, .Zy_TItle_before');
                            const titleCount = await titleEl.count();
                            if (titleCount > 0) {
                                const titleText = (await titleEl.first().innerText() || '');
                                if (/多选|不定项/.test(titleText)) qtype = 'multi';
                                else if (/判断/.test(titleText)) qtype = 'judge';
                                else if (/填空/.test(titleText)) qtype = 'fill';
                                else if (/单选/.test(titleText) || /【/.test(titleText)) qtype = 'single';
                            }
                        } catch(e) {}

                        // Count selected indicators (visual confirmation)
                        let selectedCount = 0;
                        try {
                            // Check for green checkmark classes
                            const checkEls = el.locator('.check_answer, .check_answer_dx');
                            selectedCount = await checkEls.count();
                        } catch(e) {}
                        try {
                            // Also check aria-checked on option elements
                            const ariaChecked = el.locator('[aria-checked="true"]');
                            selectedCount = Math.max(selectedCount, await ariaChecked.count());
                        } catch(e) {}

                        questions.push({
                            index: i + 1,
                            path,
                            qid,
                            qtype,
                            answer_value: answerValue,
                            selected_indicators: selectedCount,
                        });
                    } catch(e) {
                        questions.push({
                            index: i + 1,
                            path: '',
                            qid: '',
                            qtype: 'unknown',
                            error: e.message,
                        });
                    }
                }

                return JSON.stringify({
                    ok: true,
                    count: questions.length,
                    iframe_url: iframe.url().substring(0, 80),
                    questions,
                });
            } catch(e) {
                return JSON.stringify({error: 'iframe-error: ' + e.message});
            }
        }

        return JSON.stringify({error: 'no-timu-found'});
    }
    """

    sfx_json = _json.dumps(sfx)
    qdir_json = _json.dumps(script_dir.replace('\\', '/'))
    capture_js = capture_js.replace('Q_DIR', qdir_json).replace('Q_SFX', sfx_json)

    js_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False,
        dir=str(TMP_DIR), encoding="utf-8"
    )
    try:
        js_file.write(capture_js)
        js_file.close()
        raw = pw_run_code_file(js_file.name, timeout=90)
    finally:
        try:
            os.unlink(js_file.name)
        except Exception:
            pass

    result_str = pw_extract_result(raw)
    try:
        result = _json.loads(result_str)
    except _json.JSONDecodeError:
        log(f"  [FilledCap] Failed to parse result: {result_str[:120]}", "WARN")
        return []

    if not result.get("ok"):
        log(f"  [FilledCap] Screenshot failed: {result.get('error', 'unknown')}", "WARN")
        return []

    q_infos = result.get("questions", [])
    success_count = sum(1 for q in q_infos if q.get("path") and os.path.exists(q["path"]))
    selected_total = sum(q.get("selected_indicators", 0) for q in q_infos)
    answered_count = sum(1 for q in q_infos if q.get("answer_value", ""))
    log(f"  [FilledCap] Captured {success_count}/{len(q_infos)} filled screenshots "
        f"({answered_count} with answer values, {selected_total} visual indicators)")

    return q_infos


def _grade_batched(filled_infos: list[dict], ai_answers: list[dict],
                   batch_size: int = 5, section_key: str = "",
                   grade_pass_threshold: int = 80) -> dict:
    """Send filled-state screenshots to Doubao Tab1 for grading.

    Each batch of filled screenshots is uploaded; Doubao is asked to
    determine the correct answer, then compare with what's visually selected.
    This serves as an independent verification -- the solving pass gave us
    answers, and now Doubao re-evaluates with the filled screenshots.

    Returns:
        {
            accuracy: float (0-100),
            total: int,
            correct: int,
            incorrect: int,
            uncertain: int,
            per_question: [{index, selected, is_correct, correct_answer, explanation}],
            passed: bool,
        }
    """
    n = len(filled_infos)
    total_batches = math.ceil(n / batch_size)
    all_grades = []
    failed_batches = 0

    # Build AI answer lookup for per-batch reference (not all at once)
    ai_map = {}
    for a in ai_answers:
        idx = a.get("index", a.get("question_index", 0))
        ai_map[idx] = a.get("answer", "")

    log(f"  [Grading] {n} questions -> {total_batches} batch(es) of {batch_size}")

    for b in range(total_batches):
        start_idx = b * batch_size
        end_idx = min(start_idx + batch_size, n)
        batch_infos = filled_infos[start_idx:end_idx]
        batch_q_indices = [q["index"] for q in batch_infos]
        batch_paths = [q["path"] for q in batch_infos if q.get("path")]
        batch_n = len(batch_infos)

        if not batch_paths:
            log(f"  [Grading] Batch {b+1}/{total_batches}: no valid paths", "WARN")
            failed_batches += 1
            continue

        batch_label = f"{batch_q_indices[0]}-{batch_q_indices[-1]}"
        log(f"  [Grading] Batch {b+1}/{total_batches} (Q{batch_label}, {len(batch_paths)} images)...")

        # Build per-batch prompt (always uses 1-based local indexing)
        q_list_desc = "\n".join(
            f"第{i+1}张图片 = 第{batch_q_indices[i]}题"
            for i in range(batch_n)
        )
        # Per-batch AI reference (reduces bias -- only shows answers for this batch)
        ai_ref_lines = []
        for idx in batch_q_indices:
            ans = ai_map.get(idx)
            if ans is not None:
                ai_ref_lines.append(f"  Q{idx}: {_json.dumps(ans, ensure_ascii=False)}")
        ai_ref = "\n".join(ai_ref_lines) if ai_ref_lines else "(none)"

        index_list = ', '.join(str(i) for i in batch_q_indices)

        grading_prompt = (
            f"批改 {batch_n} 道概率论章节测试题。{q_list_desc}\n\n"
            f"AI参考答案（仅供参考，以截图为最终依据）：\n{ai_ref}\n\n"
            f"要求：先输出JSON再写简短分析。JSON数组必须正好{batch_n}个元素，题号依次为{index_list}。\n"
            f"格式：[{{\"index\":{batch_q_indices[0]},\"selected\":\"A\",\"is_correct\":true,"
            f"\"correct_answer\":\"A\",\"explanation\":\"理由\"}},...]\n"
            f"规则：selected=截图中绿色高亮的选项（单选字母/多选数组/看不清填unclear）；"
            f"is_correct=true/false/null；explanation=必填一句话；只返回JSON数组不要其他")

        try:
            raw_answer = ai_grade_quiz_image(batch_paths, grading_prompt, timeout=180)
            batch_grades = _parse_grade_answer(raw_answer)

            # Retry once if empty (Doubao sometimes echoes prompt without answering)
            if not batch_grades:
                log(f"  [Grading] Batch {b+1}/{total_batches}: empty, retrying with short prompt...", "WARN")
                retry_prompt = (
                    f"批改{section_key}Q{batch_label}。只输出JSON数组：\n"
                    f"[{{\"index\":{batch_q_indices[0]},\"selected\":\"?\",\"is_correct\":true,"
                    f"\"correct_answer\":\"?\",\"explanation\":\"\"}},...]\n"
                    f"题号依次为{index_list}，正好{batch_n}个。"
                )
                time.sleep(3)
                raw_answer = ai_grade_quiz_image(batch_paths, retry_prompt, timeout=120)
                batch_grades = _parse_grade_answer(raw_answer)

            if batch_grades:
                # Remap batch-local indices to global question numbers.
                # Detect whether AI returns 0-based or 1-based indices via
                # the minimum index across all batch grades.
                old_indices = [g.get("index", 0) for g in batch_grades]
                min_old = min(old_indices) if old_indices else 0
                if min_old == 0:
                    # 0-based: offset from batch start without -1
                    need_remap = True
                    idx_offset = batch_q_indices[0]
                elif min_old == 1 and batch_q_indices[0] > 1:
                    # 1-based: offset from batch start - 1
                    need_remap = True
                    idx_offset = batch_q_indices[0] - 1
                else:
                    need_remap = False
                if need_remap:
                    for g in batch_grades:
                        g["index"] = g.get("index", 0) + idx_offset

                all_grades.extend(batch_grades)
                log(f"  [Grading] Batch {b+1}/{total_batches}: {len(batch_grades)} grades", "OK")
            else:
                log(f"  [Grading] Batch {b+1}/{total_batches}: empty result", "WARN")
                failed_batches += 1
        except Exception as e:
            log(f"  [Grading] Batch {b+1}/{total_batches} exception: {e}", "WARN")
            failed_batches += 1

    # ── Summarize ──
    correct = sum(1 for g in all_grades if g.get("is_correct") is True)
    incorrect = sum(1 for g in all_grades if g.get("is_correct") is False)
    uncertain = sum(1 for g in all_grades if g.get("is_correct") is None)
    graded = correct + incorrect
    accuracy = round(correct / max(graded, 1) * 100, 1)

    if uncertain > 0 and graded == 0:
        log(f"  [Grading] WARNING: All {uncertain} questions uncertain -- "
            f"check screenshot quality or Doubao connectivity", "WARN")

    log(f"  [Grading] Total: {correct}✓ / {incorrect}✗ / {uncertain}? "
        f"= {accuracy}% accuracy ({graded} graded)")

    passed = accuracy >= grade_pass_threshold

    return {
        "accuracy": accuracy,
        "total": n,
        "correct": correct,
        "incorrect": incorrect,
        "uncertain": uncertain,
        "per_question": all_grades,
        "passed": passed,
    }


def _parse_correct_answers(snap: str) -> list[dict] | None:
    """Parse correct answers from the '查看答案' view snapshot.

    Looks for patterns like:
    - "正确答案: A" or "正确答案：B"
    - "答案: C"
    - Green checkmarks next to options
    - "√" marks indicating correct options
    - Radio/checkbox checked state

    Returns list of {index, answer} dicts, or None if parsing fails.
    """
    answers = []

    # Pattern 1: "正确答案：A" or "正确答案: B" per question
    # Often grouped: "1-5: AABBC" or individual "1. A  2. B"
    correct_patterns = [
        (r'(\d+)\s*[\.、)]\s*正确\s*答案\s*[：:]\s*([A-D]+)', None),  # "1. 正确答案：A"
        (r'第\s*(\d+)\s*题\s*[^正]*正确\s*答案\s*[：:]\s*([A-D]+)', None),  # "第1题 正确答案：A"
        (r'正确\s*答案\s*[：:]\s*([A-D]+)', 0),  # "正确答案：A" (global, assign by order)
        (r'答案\s*[：:]\s*([A-D]+)', 0),  # "答案：A" (global)
    ]

    for pattern, force_q_index in correct_patterns:
        matches = re.findall(pattern, snap, re.DOTALL | re.IGNORECASE)
        if matches:
            for i, match in enumerate(matches):
                if isinstance(match, tuple) and len(match) == 2:
                    q_idx = int(match[0])
                    ans = match[1].strip()
                else:
                    # Single group -- assign by order
                    ans = (match if isinstance(match, str) else match[0]).strip()
                    q_idx = force_q_index + i + 1 if force_q_index is not None else i + 1

                answers.append({"index": q_idx, "answer": ans})

            if answers:
                log(f"    Parsed answers (pattern {pattern[:30]}...): {answers}")
                return answers

    # Pattern 2: Look for checked/selected state in radio groups
    # In the answer view, correct options are marked with 勾 (checkmark) or highlighted
    checkmark_pattern = re.findall(
        r'radio\s+"([^"]*)"\s+\[checked\]', snap, re.IGNORECASE
    )
    if checkmark_pattern:
        for i, opt_text in enumerate(checkmark_pattern):
            answers.append({"index": i + 1, "answer": opt_text.strip()})
        if answers:
            log(f"    Parsed answers from checked radios: {answers}")
            return answers

    # Pattern 3: "√" marks next to options
    # Look for lines like "√ A. xxx" or "A. xxx √"
    tick_lines = re.findall(r'([A-D])\s*[\.、)][^\n]*[√✓]', snap)
    if tick_lines:
        for i, letter in enumerate(tick_lines):
            answers.append({"index": i + 1, "answer": letter.strip()})
        if answers:
            log(f"    Parsed answers from tick marks: {answers}")
            return answers

    # Pattern 4: Numeric answers like "1-5: ABCBD"
    seq_match = re.search(r'(\d+\s*[-–—]\s*\d+)\s*[：:]\s*([A-D]+)', snap)
    if seq_match:
        range_str = seq_match.group(1)
        ans_str = seq_match.group(2).strip()
        start_match = re.search(r'(\d+)', range_str)
        if start_match:
            start_idx = int(start_match.group(1))
            for i, ch in enumerate(ans_str):
                if ch.isalpha():
                    answers.append({"index": start_idx + i, "answer": ch.upper()})
            if answers:
                log(f"    Parsed answers from sequence '{ans_str}': {answers}")
                return answers

    return None
