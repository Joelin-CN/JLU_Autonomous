"""
Answer filling — DOM-based option clicking, blank filling, question type detection.

Uses .TiMu / .questionLi container isolation (Stage A) with .newZy_TItle
Y-coordinate fallback (Stage B) for reliable option clicking without
cross-question leakage.
"""

import json as _json
import time
import tempfile
import os

from ...constants import TMP_DIR
from ...logging_setup import log
from ...browser.engine import pw_snapshot, pw_click
from ...browser.js_runner import pw_run_code_file, pw_extract_result
from ...utils import find_ref_by_text

# AI markers indicating an unanswerable question (skip filling, count as uncertain)
UNANSWERABLE_MARKERS = [
    "unanswerable", "无法判断", "无法确定", "信息不足",
    "data insufficient", "cannot determine", "not enough info",
]


def _is_unanswerable(answer) -> bool:
    """Check if the AI indicated the question cannot be answered.

    Uses exact or prefix matching instead of substring matching to avoid
    false positives. E.g., "The answer can be determined... There is not
    enough info about option C" should NOT be flagged unanswerable just
    because it happens to contain "not enough info" in a sub-clause.
    """
    if not answer:
        return True
    answer_str = str(answer).strip().lower()
    return any(
        answer_str == m or answer_str.startswith(m)
        for m in UNANSWERABLE_MARKERS
    )


# Judge-question surface-form equivalence classes. Borrowed from
# referrence_scripts2.txt's fillQuizAnswer judge normalization (对/正确/true→A,
# 错/false→B), adapted to our text-MATCHING architecture (the reference clicks
# by data-attribute; we match option text). A judge answer the AI returns in
# ONE surface form ("对") must still match an option rendered in ANOTHER form
# ("正确" / "√" / "A. 正确"). _click_option text-matches a single form, so a
# 对/正确 mismatch silently misses. We expand to all same-polarity forms and
# try each.
_JUDGE_TRUE_FORMS = ["对", "正确", "是", "√", "T", "A"]
_JUDGE_FALSE_FORMS = ["错", "错误", "否", "×", "F", "B"]


def _judge_answer_variants(answer) -> list:
    """Expand a judge answer to all equivalent same-polarity surface forms.

    The ORIGINAL answer is always returned FIRST (so existing behavior is
    preserved — the original form is tried before any variant), followed by the
    other forms of the SAME polarity, de-duplicated. Polarity is NEVER crossed:
    a "true" answer never expands to a "false" form.

    Returns [answer] unchanged when the answer is not a recognizable judge token
    (so callers can use this unconditionally for judge-typed questions without
    risking nonsense expansion of, e.g., a stray essay string). Non-str answers
    are returned as a single-element list untouched.
    """
    if not isinstance(answer, str):
        return [answer]
    norm = answer.strip().lower()
    if norm in {f.lower() for f in _JUDGE_TRUE_FORMS}:
        forms = _JUDGE_TRUE_FORMS
    elif norm in {f.lower() for f in _JUDGE_FALSE_FORMS}:
        forms = _JUDGE_FALSE_FORMS
    else:
        return [answer]  # not a judge token — leave untouched
    # Original first, then the rest of its polarity class, de-duplicated.
    out = [answer]
    for f in forms:
        if f not in out and f.lower() != norm:
            out.append(f)
    return out


def _detect_question_types() -> list[dict]:
    """Inspect quiz DOM to determine each question's type.

    Returns list of {index: int, type: str, optionCount: int, hasTextarea: bool}
    where type is one of: 'single', 'multi', 'judge', 'fill', 'essay', 'unknown'.

    PRIMARY anchor: the hidden ``input[id^="answertype"]`` Chaoxing renders
    inside each ``.TiMu`` — its value encodes the type directly
    (0=single 1=multi 2=fill 3=judge 4=essay), same field the reference
    script's collectQuizQuestions reads. This is authoritative: ``.TiMu``
    options are styled ``<li>`` (no radio/checkbox inputs and a fixed
    option count), so a 4-option single is structurally indistinguishable
    from a 4-option multi — the old optionCount heuristic misclassified
    EVERY single as multi.

    FALLBACK heuristic (only when the answertype field is absent, e.g.
    non-.TiMu templates), mirrors referrence_scripts.txt:
      - input[type="checkbox"] -> multi
      - input[type="radio"] + 2 options(对/错) -> judge
      - input[type="radio"] -> single
      - textarea / contenteditable -> fill / essay
      - >0 options -> single (fallback)
    """
    js = r"""
    async (page) => {
        const candidates = page.frames().filter(f =>
            f !== page.mainFrame() &&
            (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
             f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
        );
        if (candidates.length === 0) return JSON.stringify({ok: false, reason: 'no-iframe'});

        let containers = [];
        let quizIframe = null;

        // Find containers (.TiMu for zj, .questionLi for zy/ks)
        for (const iframe of candidates) {
            for (const containerSel of ['.TiMu', '.questionLi']) {
                try {
                    const els = iframe.locator(containerSel);
                    const c = await els.count();
                    if (c >= 1) {
                        quizIframe = iframe;
                        for (let i = 0; i < c; i++) {
                            containers.push({el: els.nth(i), idx: i});
                        }
                        break;
                    }
                } catch(e) {}
            }
            if (containers.length > 0) break;
        }

        // Fallback: no containers found — try counting via .newZy_TItle
        if (containers.length === 0) {
            for (const iframe of candidates) {
                try {
                    const titleEls = iframe.locator('.newZy_TItle, .Zy_TItle');
                    const c = await titleEls.count();
                    if (c >= 2) {
                        // Each question has 2 titles, so c/2 ≈ question count
                        const qCount = Math.floor(c / 2);
                        for (let i = 0; i < qCount; i++) {
                            containers.push({el: null, idx: i});
                        }
                        break;
                    }
                } catch(e) {}
            }
        }

        if (containers.length === 0) {
            return JSON.stringify({ok: false, reason: 'no-containers'});
        }

        const results = [];

        for (const {el, idx} of containers) {
            const qIndex = idx + 1;
            let qType = 'unknown';
            let optionCount = 0;
            let hasTextarea = false;
            let hasCheckbox = false;
            let hasRadio = false;
            let answerType = null;  // raw input[id^=answertype] value, if present
            let optionTexts = [];   // hoisted: referenced by fallback judge branch below

            if (el) {
                try {
                    // PRIMARY ANCHOR: Chaoxing renders a hidden
                    // input[id^="answertype"] inside each .TiMu whose value
                    // directly encodes the question type (same field the
                    // reference script's collectQuizQuestions reads):
                    //   0=single 1=multi 2=fill 3=judge 4=short/essay
                    // This is authoritative — .TiMu options are styled <li>
                    // (no radio/checkbox inputs), so a 4-option single is
                    // structurally identical to a 4-option multi and the
                    // optionCount heuristic below CANNOT tell them apart
                    // (it misclassified every single as multi). When the
                    // field is present we trust it; otherwise we fall back
                    // to the structural heuristic for non-.TiMu templates.
                    try {
                        const atLoc = el.locator('input[id^="answertype"]');
                        if ((await atLoc.count()) > 0) {
                            const v = (await atLoc.first().getAttribute('value') || '').trim();
                            answerType = v;
                        }
                    } catch(e) {}

                    // Detect text inputs
                    const textareas = await el.locator(
                        'textarea').count();
                    const inputs = await el.locator(
                        'input[type="text"], input:not([type]), [contenteditable="true"]').count();
                    hasTextarea = (textareas + inputs) > 0;

                    // Detect checkbox (multi-select)
                    hasCheckbox = (await el.locator(
                        'input[type="checkbox"]').count()) > 0;

                    // Detect radio (single-select or judge)
                    hasRadio = (await el.locator(
                        'input[type="radio"]').count()) > 0;

                    // Count option elements
                    let zjOpts = 0, zyOpts = 0;
                    try { zjOpts = await el.locator(
                        '[class*="before-after"]').count(); } catch(e) {}
                    try { zyOpts = await el.locator(
                        '.answerBg').count(); } catch(e) {}
                    optionCount = Math.max(zjOpts, zyOpts);

                    // Get option texts for judge detection
                    if (optionCount === 2 && (hasRadio || !hasCheckbox)) {
                        try {
                            const optEls = await el.locator(
                                zjOpts > 0 ? '[class*="before-after"] .fl.after'
                                           : '.answerBg .answer_p').all();
                            for (const oe of optEls) {
                                try {
                                    const t = (await oe.innerText() || '').trim();
                                    if (t) optionTexts.push(t);
                                } catch(e) {}
                            }
                        } catch(e) {}
                    }
                } catch(e) {}
            }

            // PRIMARY: trust the answertype hidden field when present.
            const ANSWERTYPE_MAP = {
                '0': 'single', '1': 'multi', '2': 'fill',
                '3': 'judge', '4': 'essay',
            };
            if (answerType !== null && ANSWERTYPE_MAP[answerType]) {
                qType = ANSWERTYPE_MAP[answerType];
            } else if (hasTextarea && optionCount <= 1) {
                // FALLBACK heuristic (templates without answertype field).
                qType = optionCount === 0 ? 'essay' : 'fill';
            } else if (hasCheckbox) {
                qType = 'multi';
            } else if (hasRadio && optionCount === 2) {
                // Check if options look like 对/错 (true/false)
                const isJudge = optionTexts.length === 2 &&
                    optionTexts.some(t =>
                        /^(正确|错误|对|错|√|×|True|False|true|false|是|否)$/i.test(
                            t.replace(/[\s.、)]/g, '')));
                qType = isJudge ? 'judge' : 'single';
            } else if (hasRadio) {
                qType = 'single';
            } else if (optionCount >= 4) {
                // No radio/checkbox inputs, many options — likely multi-select
                // (Chaoxing .TiMu format uses styled li, not form inputs)
                qType = 'multi';
            } else if (optionCount > 0) {
                qType = 'single';
            } else if (hasTextarea) {
                qType = 'essay';
            }

            results.push({
                index: qIndex,
                type: qType,
                optionCount: optionCount,
                hasTextarea: hasTextarea,
                hasCheckbox: hasCheckbox,
                hasRadio: hasRadio,
                answerType: answerType,
            });
        }

        return JSON.stringify({ok: true, types: results, containerCount: containers.length});
    }
    """

    js_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(TMP_DIR), encoding='utf-8')
    try:
        js_file.write(js)
        js_file.close()
        raw = pw_run_code_file(js_file.name, timeout=15)
    finally:
        try:
            os.unlink(js_file.name)
        except Exception:
            pass

    result_str = pw_extract_result(raw)
    try:
        result = _json.loads(result_str)
        if result.get("ok"):
            types = result.get("types", [])
            # Summary log
            type_counts = {}
            for t in types:
                type_counts[t["type"]] = type_counts.get(t["type"], 0) + 1
            log(f"  Question types detected ({result.get('containerCount', len(types))} containers): "
                f"{type_counts}")
            return types
    except _json.JSONDecodeError:
        log(f"  Question type detection parse error: {result_str[:100]}", "WARN")
    return []


def _fill_answers(answers: list[dict]) -> int:
    """Fill in answers (no submit).  Returns count of questions filled.

    Uses DOM question-type detection to dispatch properly:
      - multi: click each option in the list
      - single/judge: click one option
      - fill/essay: delegated to _fill_blank
      - unknown: fall back to _click_option

    Questions marked as unanswerable by the AI are skipped (not filled).
    """
    # Detect question types from DOM for proper dispatch
    q_types = _detect_question_types()
    type_map = {t["index"]: t["type"] for t in q_types} if q_types else {}

    if not answers:
        return 0
    filled = 0
    for ans in answers:
        idx = ans.get("index", ans.get("question_index", 0))
        answer = ans.get("answer", "")
        q_type = type_map.get(idx, "unknown")

        # Unanswerable question check
        if _is_unanswerable(answer):
            log(f"  Q{idx}: AI marked unanswerable — skipping fill", "WARN")
            continue

        if q_type in ("fill", "essay"):
            # Fill-in-the-blank / essay
            if not _fill_blank(idx, answer):
                log(f"  Q{idx}: fill-blank failed, trying _click_option fallback", "WARN")
                _click_option(idx, answer)
        elif isinstance(answer, list):
            # Multi-select: click each option
            for opt in answer:
                _click_option(idx, opt)
        elif q_type == "judge":
            # Judge: the AI may return one surface form ("对") while the option
            # renders as another ("正确"/"√"/"A"). Try same-polarity variants in
            # order (original first) until one clicks; stop at first success so
            # we never select two options. See _judge_answer_variants.
            for variant in _judge_answer_variants(answer):
                if _click_option(idx, variant):
                    break
        else:
            # Single select / unknown: click one option
            _click_option(idx, answer)
        filled += 1

    return filled


def _click_option(q_index: int, answer: str) -> bool:
    """Click a radio/checkbox for question q_index. Returns True if an option
    was clicked (via DOM scope or snapshot fallback), False if none matched.

    PRIMARY: Uses DOM-based question boundary detection via
    .newZy_TItle / .Zy_TItle elements (same approach as
    _capture_question_screenshots). This is reliable because
    Chaoxing quiz pages use these DOM elements for question
    numbering, NOT text markers like "1." or "第1题" (which
    produce false positives from URLs, chapter numbers, etc.).

    FALLBACK: Snapshot text search (for non-standard quiz layouts).
    """
    answer_str = str(answer).strip()
    is_single_letter = len(answer_str) == 1 and answer_str.isalpha()

    # PRIMARY: DOM-based scoped click
    if _click_option_dom(q_index, answer_str, is_single_letter):
        return True

    # FALLBACK: Snapshot text-based search
    snap = pw_snapshot()
    option_ref = find_ref_by_text(snap, answer_str)
    if option_ref:
        pw_click(option_ref)
        time.sleep(0.3)
        return True

    # Try letter matching in snapshot
    if is_single_letter:
        for pat in [f"{answer_str}.", f"{answer_str}、", f"{answer_str})"]:
            letter_ref = find_ref_by_text(snap, pat)
            if letter_ref:
                pw_click(letter_ref)
                time.sleep(0.3)
                return True

    log(f"  Could not find option for Q{q_index}: {answer_str}", "WARN")
    return False


def _click_option_dom(q_index: int, answer_str: str,
                       is_single_letter: bool) -> bool:
    """DOM-based option click using .TiMu / .questionLi container isolation.

    Two-stage strategy (matching 3 reference scripts in etc/):
      Stage A (PRIMARY): .TiMu / .questionLi containers + querySelectorAll
        within each container -> natural isolation, no cross-question leakage.
      Stage B (FALLBACK): .newZy_TItle / .Zy_TItle Y-coordinate scoping
        (kept for non-standard quiz layouts).

    Both stages include:
      - aria-checked / .check_answer / .check_answer_dx already-selected guard
      - Normalized whitespace text matching (fixes length-limit false negatives)
    """
    safe_answer = _json.dumps(answer_str)
    zidx = q_index - 1  # Zero-based container index

    js = f"""
    async (page) => {{
        const candidates = page.frames().filter(f =>
            f !== page.mainFrame() &&
            (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
             f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
        );
        if (candidates.length === 0) return JSON.stringify({{ok: false, reason: 'no-iframe'}});

        const isSingleLetter = {_json.dumps(is_single_letter)};
        const answerText = {safe_answer};

        // ── Shared helpers ──
        const normText = (s) => {{
            // Collapse all whitespace (incl. non-breaking), strip common punctuation
            return (s || '').replace(/[\\s\\u00A0]+/g, ' ')
                .replace(/[.、)\\uFF09\\uff0c\\u3001]/g, '')
                .trim();
        }};

        const isAlreadySelected = async (el) => {{
            // PRIMARY: Check input#answer{{qid}}.value — Chaoxing stores
            // the user's answer in a hidden input with id="answer{{questionId}}".
            // This is more reliable than aria-checked (which can be stale)
            // or .check_answer (which sometimes doesn't get added).
            try {{
                // Find the answer input — search from container root upward
                const container = el.closest('.TiMu, .questionLi');
                const root = container || el;
                const answerInput = await root.evaluate(node => {{
                    const inp = node.querySelector('input[id^="answer"]');
                    return inp ? {{ id: inp.id, value: inp.value }} : null;
                }});
                if (answerInput && answerInput.value && answerInput.value.trim() !== '') {{
                    return true;
                }}
            }} catch(e) {{}}

            // SECONDARY: aria-checked on element or parent
            try {{
                const ariaChecked = await el.getAttribute('aria-checked');
                if (ariaChecked === 'true') return true;
                const parentAria = await el.evaluate(e => {{
                    const p = e.parentElement;
                    return p ? p.getAttribute('aria-checked') : null;
                }});
                if (parentAria === 'true') return true;
            }} catch(e) {{}}

            // TERTIARY: visual check classes / input:checked
            try {{
                const hasCheck = await el.evaluate(e => {{
                    return !!(e.querySelector('.check_answer') ||
                              e.querySelector('.check_answer_dx') ||
                              e.querySelector('input:checked'));
                }});
                if (hasCheck) return true;
            }} catch(e) {{}}
            return false;
        }};

        const matchText = (text) => {{
            if (!text) return false;
            const nt = normText(text);
            if (!nt) return false;
            const na = normText(answerText);
            if (!na) return false;

            if (isSingleLetter) {{
                // Strict: first character of option must match the answer letter.
                // Use charAt(0) rather than strip-all-non-alpha so that "B"
                // does NOT match an option whose text starts with "Bayesian"
                // when that option is in a different question container.
                const firstChar = nt.trim().charAt(0);
                if (firstChar && firstChar.toUpperCase() === na.toUpperCase() &&
                    nt.length <= 3) return true;
                // Also match if the option text starts with exactly the letter
                // followed by punctuation (e.g., "B. Bayesian")
                if (nt.length >= 2 && nt.charAt(0).toUpperCase() === na.toUpperCase() &&
                    /^[.、)）]/.test(nt.charAt(1))) return true;
            }} else {{
                // Full-text normalized comparison (no includes() to avoid
                // false positives like short answers matching substrings)
                if (nt === na) return true;
                if (nt.startsWith(na) || na.startsWith(nt)) return true;
            }}
            return false;
        }};

        // ── Stage A: .TiMu / .questionLi container isolation ──
        let quizIframe = null;
        let stageA_method = null;

        for (const iframe of candidates) {{
            for (const containerSel of ['.TiMu', '.questionLi']) {{
                try {{
                    const containers = iframe.locator(containerSel);
                    const c = await containers.count();
                    if (c > {zidx}) {{
                        quizIframe = iframe;
                        stageA_method = 'container-' + containerSel.replace('.', '');
                        const container = containers.nth({zidx});

                        // Determine option elements based on container type
                        let optionEls = [];
                        if (containerSel === '.TiMu') {{
                            // zj type: options in [class*="before-after"] elements
                            optionEls = await container.locator(
                                '[class*="before-after"]').all();
                        }} else {{
                            // zy/ks type: options in .answerBg elements
                            optionEls = await container.locator('.answerBg').all();
                        }}

                        // Fallback: try generic option selectors within container
                        if (optionEls.length === 0) {{
                            optionEls = await container.locator(
                                'label, [role="radio"], [role="checkbox"], ' +
                                'li[onclick], .num_option, .option_item').all();
                        }}

                        // Try each option within the container
                        for (const el of optionEls) {{
                            try {{
                                if (await isAlreadySelected(el)) continue;

                                const text = (await el.innerText() || '').trim();
                                if (matchText(text)) {{
                                    await el.click();
                                    await page.waitForTimeout(200);
                                    return JSON.stringify({{
                                        ok: true,
                                        method: stageA_method,
                                        text: text.substring(0, 60),
                                        containerIdx: {zidx},
                                    }});
                                }}
                            }} catch(e) {{}}
                        }}

                        // If we have a container but no match, also try clicking
                        // option text elements within the container
                        for (const el of optionEls) {{
                            try {{
                                if (await isAlreadySelected(el)) continue;
                                // Try child text elements (.fl.after, .answer_p)
                                for (const textSel of ['.fl.after', '.answer_p',
                                                       '.num_option', 'span']) {{
                                    try {{
                                        const textEls = await el.locator(textSel).all();
                                        for (const tel of textEls) {{
                                            const text = (await tel.innerText() || '').trim();
                                            if (matchText(text)) {{
                                                // Click the parent option element
                                                await el.click();
                                                await page.waitForTimeout(200);
                                                return JSON.stringify({{
                                                    ok: true,
                                                    method: stageA_method,
                                                    text: text.substring(0, 60),
                                                    containerIdx: {zidx},
                                                    childSel: textSel,
                                                }});
                                            }}
                                        }}
                                    }} catch(e) {{}}
                                }}
                            }} catch(e) {{}}
                        }}

                        // Container found but no match — report and skip to fallback
                        return JSON.stringify({{
                            ok: false,
                            reason: 'container-no-match',
                            method: stageA_method,
                            containerIdx: {zidx},
                            optionCount: optionEls.length,
                        }});
                    }}
                }} catch(e) {{}}
            }}
            if (quizIframe) break;
        }}

        // ── Stage B: .newZy_TItle Y-coordinate fallback ──
        // (kept for quiz pages without .TiMu / .questionLi containers)
        let titleBoxes = [];

        for (const iframe of candidates) {{
            try {{
                const els = iframe.locator('.newZy_TItle, .Zy_TItle');
                const c = await els.count();
                if (c >= 1) {{
                    for (let i = 0; i < c; i++) {{
                        try {{
                            const box = await els.nth(i).boundingBox();
                            if (box && box.width > 30 && box.height > 10) {{
                                titleBoxes.push({{
                                    y: Math.round(box.y),
                                    h: Math.round(box.height),
                                }});
                            }}
                        }} catch(e) {{}}
                    }}
                    if (titleBoxes.length > 0) {{
                        quizIframe = iframe;
                        break;
                    }}
                }}
            }} catch(e) {{}}
        }}

        if (titleBoxes.length === 0) {{
            return JSON.stringify({{ok: false, reason: 'no-containers-and-no-titles'}});
        }}

        // Sort by Y and dedup (merge within 10px — same question ×2 titles)
        titleBoxes.sort((a, b) => a.y - b.y);
        let deduped = [];
        for (const tb of titleBoxes) {{
            const last = deduped[deduped.length - 1];
            if (last && Math.abs(tb.y - last.y) <= 10) {{
                if (tb.y < last.y) {{ last.y = tb.y; }}
            }} else {{
                deduped.push({{...tb}});
            }}
        }}

        if ({zidx} >= deduped.length) {{
            return JSON.stringify({{ok: false, reason: 'index-out-of-range',
                max: deduped.length}});
        }}

        const startY = deduped[{zidx}].y;
        let endY;
        if ({zidx} + 1 < deduped.length) {{
            endY = deduped[{zidx} + 1].y - 4;
        }} else {{
            endY = startY + 800;
        }}

        // Option selectors for Y-coord scanning (zj -> zy/ks priority)
        const ySelectors = [
            '[class*="before-after"]',
            '.answerBg',
            'li.font-cxsecret',
            'label.fl.before',
            'span.num_option',
            'label',
        ];

        for (const sel of ySelectors) {{
            try {{
                const els = await quizIframe.locator(sel).all();
                for (const el of els) {{
                    try {{
                        const box = await el.boundingBox();
                        if (!box || box.y < startY || box.y > endY) continue;
                        if (box.width < 12 || box.height < 8) continue;

                        if (await isAlreadySelected(el)) continue;

                        const text = (await el.innerText() || '').trim();
                        if (matchText(text)) {{
                            await el.click();
                            await page.waitForTimeout(200);
                            return JSON.stringify({{
                                ok: true,
                                method: 'y-coord-fallback',
                                text: text.substring(0, 60),
                                y: Math.round(box.y),
                                sel: sel,
                            }});
                        }}
                    }} catch(e) {{}}
                }}
            }} catch(e) {{}}
        }}

        return JSON.stringify({{
            ok: false,
            reason: 'no-match-in-range',
            startY: Math.round(startY),
            endY: Math.round(endY),
            totalQuestions: deduped.length,
        }});
    }}
    """

    js_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(TMP_DIR), encoding='utf-8')
    try:
        js_file.write(js)
        js_file.close()
        raw = pw_run_code_file(js_file.name, timeout=20)
    finally:
        try:
            os.unlink(js_file.name)
        except Exception:
            pass

    result_str = pw_extract_result(raw)
    try:
        result = _json.loads(result_str)
    except _json.JSONDecodeError:
        log(f"  DOM click result parse error: {result_str[:100]}", "WARN")
        return False

    if result.get("ok"):
        log(f"  Q{q_index} DOM click: {result.get('text', '?')} "
            f"(method={result.get('method', '?')})")
        time.sleep(0.3)
        return True

    # Log failure details for debugging
    log(f"  Q{q_index} DOM miss: {result.get('reason', '?')} "
        f"(method={result.get('method', '?')}, "
        f"Y={result.get('startY', '?')}..{result.get('endY', '?')}, "
        f"optionCount={result.get('optionCount', '?')}, "
        f"totalQ={result.get('totalQuestions', '?')})", "WARN")
    return False


def _fill_blank(q_index: int, answer: str) -> bool:
    """Fill a textarea/blank question using UE editor or value assignment.

    Reference scripts (referrence_scripts.txt:5352-5363,
    referrence_scripts3.txt:2713-2722) use:
        const ueditor = this._window.UE.getEditor(textareaElement.name);
        ueditor.setContent(answer);

    Falls back to direct value assignment + dispatchEvent if UE unavailable.
    """
    safe_answer = _json.dumps(str(answer))
    zidx = q_index - 1  # zero-based container index

    js = f"""
    async (page) => {{
        const candidates = page.frames().filter(f =>
            f !== page.mainFrame() &&
            (f.url().includes('doHomeWorkNew') || f.url().includes('mooc-ans/work') ||
             f.url().includes('knowledge/cards') || f.url().includes('mooc2-ans'))
        );
        if (candidates.length === 0) return JSON.stringify({{ok: false, reason: 'no-iframe'}});

        const answerText = {safe_answer};
        let quizIframe = null;
        let textareas = [];

        // ── Strategy 1: .TiMu / .questionLi container scoping ──
        for (const iframe of candidates) {{
            for (const containerSel of ['.TiMu', '.questionLi']) {{
                try {{
                    const containers = iframe.locator(containerSel);
                    const c = await containers.count();
                    if (c > {zidx}) {{
                        quizIframe = iframe;
                        const container = containers.nth({zidx});

                        // Find all text input elements within this container
                        const taEls = await container.locator(
                            'textarea, input[type="text"], input:not([type]), ' +
                            '[contenteditable="true"]'
                        ).all();
                        for (const el of taEls) {{
                            textareas.push(el);
                        }}
                        break;
                    }}
                }} catch(e) {{}}
            }}
            if (textareas.length > 0) break;
        }}

        // ── Strategy 2: .newZy_TItle Y-coordinate fallback ──
        if (textareas.length === 0) {{
            for (const iframe of candidates) {{
                try {{
                    const titleEls = iframe.locator('.newZy_TItle, .Zy_TItle');
                    const c = await titleEls.count();
                    if (c <= {zidx}) continue;

                    quizIframe = iframe;
                    const titleBox = await titleEls.nth({zidx}).boundingBox();
                    if (!titleBox) continue;

                    let endY;
                    if ({zidx} + 1 < c) {{
                        const nextBox = await titleEls.nth({zidx} + 1).boundingBox();
                        endY = nextBox ? Math.round(nextBox.y - 4) : Math.round(titleBox.y + 800);
                    }} else {{
                        endY = Math.round(titleBox.y + 800);
                    }}

                    const allTextareas = await iframe.locator(
                        'textarea, input[type="text"], input:not([type]), ' +
                        '[contenteditable="true"]'
                    ).all();
                    for (const ta of allTextareas) {{
                        const box = await ta.boundingBox();
                        if (box && box.y >= titleBox.y && box.y <= endY) {{
                            textareas.push(ta);
                        }}
                    }}
                    if (textareas.length > 0) break;
                }} catch(e) {{}}
            }}
        }}

        if (textareas.length === 0) {{
            return JSON.stringify({{ok: false, reason: 'no-textarea-found', index: {zidx}}});
        }}

        // ── Fill each textarea ──
        let filledCount = 0;
        let method = 'value-assign';

        for (const ta of textareas) {{
            try {{
                const name = await ta.getAttribute('name');

                // PRIMARY: UE editor API (Chaoxing's rich text editor)
                if (name) {{
                    try {{
                        const ueSuccess = await quizIframe.evaluate(
                            (opts) => {{
                                if (typeof UE !== 'undefined' && UE.getEditor) {{
                                    const editor = UE.getEditor(opts.name);
                                    if (editor && typeof editor.setContent === 'function') {{
                                        editor.setContent(opts.value);
                                        return true;
                                    }}
                                }}
                                return false;
                            }},
                            {{name: name, value: answerText}}
                        );
                        if (ueSuccess) {{
                            method = 'UE.setContent';
                            filledCount++;
                            continue;
                        }}
                    }} catch(e) {{}}
                }}

                // FALLBACK: Direct value assignment + dispatch events
                await quizIframe.evaluate(
                    (opts) => {{
                        const el = document.querySelector(
                            'textarea[name="' + opts.name + '"], ' +
                            'input[name="' + opts.name + '"], ' +
                            '[contenteditable="true"][name="' + opts.name + '"]'
                        );
                        if (el) {{
                            if (el.getAttribute('contenteditable') === 'true') {{
                                el.textContent = opts.value;
                            }} else {{
                                el.value = opts.value;
                            }}
                            el.dispatchEvent(new Event('input', {{bubbles: true}}));
                            el.dispatchEvent(new Event('change', {{bubbles: true}}));
                            el.dispatchEvent(new Event('blur', {{bubbles: true}}));
                        }}
                    }},
                    {{name: name, value: answerText}}
                );
                filledCount++;
            }} catch(e) {{}}
        }}

        return JSON.stringify({{
            ok: filledCount > 0,
            method: method,
            textareasFound: textareas.length,
            filledCount: filledCount,
            answerLen: answerText.length,
        }});
    }}
    """

    js_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(TMP_DIR), encoding='utf-8')
    try:
        js_file.write(js)
        js_file.close()
        raw = pw_run_code_file(js_file.name, timeout=15)
    finally:
        try:
            os.unlink(js_file.name)
        except Exception:
            pass

    result_str = pw_extract_result(raw)
    try:
        result = _json.loads(result_str)
        if result.get("ok"):
            log(f"  Q{q_index} fill-blank: {result.get('filledCount', 0)} filled "
                f"(method={result.get('method', '?')}, "
                f"answerLen={result.get('answerLen', 0)})")
            time.sleep(0.3)
            return True
    except _json.JSONDecodeError:
        log(f"  Q{q_index} fill-blank parse error: {result_str[:100]}", "WARN")

    log(f"  Q{q_index} fill-blank failed: {result.get('reason', '?')}", "WARN")
    return False
