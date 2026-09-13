"""智慧树章节测验/作业求解器（M4）——抽取 → AI 作答 → 填答 → 提交。

架构对齐超星 ``platforms/chaoxing/solvers/quiz/``（抽取→AI→填答→提交），
瘦身为单文件双策略（文本优先、截图兜底）；AI 路由复用 ``core.ai.router``
（豆包/DeepSeek，配置同源 ``chaoxing_config.json``，零平台耦合）。

选择器词汇（M0 调研 + 2026-09-12 本地交叉验证，见
``docs/reports/analysis/ZHIHUISHU_ANALYSIS_2026-09-12.md`` §4）：
    - 章测入口：章节树 ``li.chapter-test``
    - 作业/测验页（stuExamWeb 同构）：``.examPaper_subject`` 题块、
      ``.subject_describe`` 题干、``.examquestions-answer .subject_node`` 选项
    - 题型标记：``.title-tit`` / ``.subject_type``（【单选题】等）

反自动化红线（分析报告 Q5 / D6 同源纪律）：
    - 只用真实点击（pw click，可信事件）；JS 仅只读取值
    - 真实提交之间 60–120s 随机节奏（dry_run / grade_only 跳过）
    - grade_only（模拟运行）：完整导航→抽取→AI→填答，**绝不提交**

安全档位（对齐超星语义）：
    - ``dry_run``：进入即返回，零导航零提交
    - ``grade_only``：填答不提交（真机验证/模拟运行模式，人工接管提交）
"""

import json
import random
import re
import time

from core.constants import TMP_DIR
from core.logging_setup import log, ticket, check_signals
from core.browser.engine import pw_snapshot, pw_click, pw_goto
from core.browser.js_runner import _run_js_file, pw_extract_result
from core.utils import find_ref_by_text, human_delay

from platforms.zhihuishu.constants import build_study_url
from platforms.zhihuishu.video import scroll_load_chapter_tree

# 真实提交之间的随机节奏（秒）——对齐超星 solver 的 60–120s 拟人间隔
_SUBMIT_PACING_S = (60.0, 120.0)

# 题型标记 → 抽象类型（与超星 solvers single/multi/judge/fill/essay 同构）
_TYPE_MARKERS = [
    ("单选", "single"),
    ("多选", "multi"),
    ("判断", "judge"),
    ("填空", "fill"),
    ("简答", "essay"),
    ("名词解释", "essay"),
    ("论述", "essay"),
]

# 选项节点 CSS（抽取与点击共用同一条链，保证 nth 全局索引一致）
_OPTION_CSS = ".examquestions-answer .subject_node"


# ── 纯函数（单测直测，无浏览器）──────────────────────────────────────


def detect_question_type(type_text: str, option_count: int) -> str:
    """按题型标记文本判型；无标记时按选项数启发（2 项 → 判断，否则单选）。"""
    text = (type_text or "").strip()
    for marker, kind in _TYPE_MARKERS:
        if marker in text:
            return kind
    if option_count == 2:
        return "judge"
    return "single"


def parse_answer_letters(answer) -> list:
    """把 AI 答案归一为选项字母表：'AC' / ['A','C'] / 'A,C' → ['A','C']。"""
    if answer is None:
        return []
    if isinstance(answer, list):
        parts = [str(a) for a in answer]
    else:
        parts = re.split(r"[,，\s]+", str(answer))
    letters = []
    for part in parts:
        for ch in part.strip():
            if "A" <= ch.upper() <= "Z" and ch.isalpha():
                letters.append(ch.upper())
    # 去重保序
    return list(dict.fromkeys(letters))


def judge_answer_index(answer) -> int:
    """判断题答案 → 选项序号：正确/对 → 0，错误/错 → 1；无法解析 → -1。"""
    text = str(answer if not isinstance(answer, list) else (answer[0] if answer else ""))
    if re.search(r"正确|对$|√|true", text, re.IGNORECASE):
        return 0
    if re.search(r"错误|错$|×|false", text, re.IGNORECASE):
        return 1
    return -1


def parse_score(text: str):
    """从页面快照文本解析得分（对齐超星 submitter 的正则族）；无匹配 → None。"""
    if not text:
        return None
    m = (re.search(r"得分[：:]\s*(\d+)", text)
         or re.search(r"(\d+(?:\.\d+)?)\s*分", text)
         or re.search(r"(\d+)\s*%", text))
    if not m:
        return None
    try:
        return int(float(m.group(1)))
    except ValueError:
        return None


def build_ai_questions(questions: list) -> list:
    """把抽取的题块组装为 AI 路由入参 [{index, text}]（题型标注 + 选项枚举）。"""
    out = []
    for i, q in enumerate(questions, 1):
        lines = [f"【{q.get('type', 'single')}】{q.get('stem', '').strip()}"]
        for j, opt in enumerate(q.get("options", [])):
            lines.append(f"{chr(65 + j)}. {opt}")
        out.append({"index": i, "text": "\n".join(lines)})
    return out


def parse_reveal_letters(raw: str) -> list:
    """弹题揭示文本 → 字母表（如「正确答案：A,C」→ ['A','C']）。"""
    m = re.search(r"正确答案[：:]\s*([A-Z,，\s]+)", raw or "")
    return [c for c in (m.group(1) if m else "") if "A" <= c <= "Z"]


# ── 只读探测（JS 仅取值，不驱动）────────────────────────────────────


def _run_json(js: str, timeout: int = 20):
    raw = _run_js_file(js, timeout=timeout)
    data = json.loads(pw_extract_result(raw) or raw)
    if isinstance(data, str):
        data = json.loads(data)
    return data


_EXTRACT_JS = """
async (page) => {
  const r = await page.evaluate(() => {
    const subjects = [...document.querySelectorAll('.examPaper_subject')];
    const items = subjects.map(s => {
      const typeEl = s.querySelector('.subject_type, .title-tit');
      const stem = (s.querySelector('.subject_describe') || s.querySelector('.subject_node p') || {}).innerText || '';
      const options = [...s.querySelectorAll('%OPTION_CSS%')]
        .map(o => (o.innerText || '').trim().slice(0, 80)).filter(Boolean);
      return {typeText: ((typeEl || {}).innerText || '').trim(), stem: stem.trim(), options};
    });
    return JSON.stringify({items, url: location.href});
  });
  return r;
}
"""


def extract_exam_questions() -> list:
    """只读抽取测验页题块 [{typeText, stem, options}]（与 _OPTION_CSS 同链）。"""
    js = _EXTRACT_JS.replace("%OPTION_CSS%", _OPTION_CSS)
    try:
        data = _run_json(js, timeout=25)
    except Exception as e:
        log(f"测验题面抽取失败：{e}", "WARN")
        return []
    return data.get("items", [])


def count_option_nodes() -> int:
    """只读统计当前页选项节点总数（填答 nth 索引的对账口径）。"""
    js = """
async (page) => {
  const r = await page.evaluate(() => {
    return JSON.stringify({n: document.querySelectorAll('%CSS%').length});
  });
  return r;
}
""".replace("%CSS%", _OPTION_CSS)
    try:
        return int(_run_json(js, timeout=15).get("n", 0))
    except Exception:
        return 0


def _fullpage_screenshot(path: str) -> bool:
    """整页截图（截图兜底策略的数据源；JS 仅截图不改状态）。"""
    js = """
async (page) => {
  await page.screenshot({path: '%PATH%', fullPage: true});
  return JSON.stringify({ok: true});
}
""".replace("%PATH%", path.replace("\\", "/").replace("'", "\\'"))
    try:
        _run_json(js, timeout=40)
        return True
    except Exception as e:
        log(f"整页截图失败：{e}", "WARN")
        return False


# ── 填答 / 提交（真实点击）─────────────────────────────────────────


def _click_option(global_nth: int, what: str) -> bool:
    """按全局 nth 点击选项节点（与抽取 JS 同链，索引口径一致）。"""
    try:
        from core.browser.engine import pw
        pw("click", f"{_OPTION_CSS} >> nth={global_nth}",
           timeout=10)
        return True
    except Exception as e:
        log(f"点击 {what} 失败：{e}", "WARN")
        return False


def fill_answers(questions: list, answers: list) -> int:
    """按 AI 答案填答，返回成功填答的题数。

    - single/judge：单击对应选项（judge 由「正确/错误」映射序号）
    - multi：逐个点击字母对应项
    - fill：经快照 textbox ref 填写；找不到输入框则留空告警
    - essay：留空（AI 不做简答提交，降低风险）
    """
    by_index = {a.get("index"): a.get("answer") for a in answers}
    filled = 0
    offset = 0
    for i, q in enumerate(questions, 1):
        qtype = q.get("type", "single")
        opts = q.get("options", [])
        answer = by_index.get(i)
        ok = False
        if qtype in ("single", "multi"):
            letters = parse_answer_letters(answer)
            for letter in letters:
                nth = offset + (ord(letter) - ord("A"))
                if 0 <= nth - offset < len(opts):
                    ok = _click_option(nth, f"第{i}题选项{letter}") or ok
                    human_delay(0.6, 0.15)
        elif qtype == "judge":
            idx = judge_answer_index(answer)
            if 0 <= idx < len(opts):
                ok = _click_option(offset + idx, f"第{i}题判断项{idx}")
                human_delay(0.6, 0.15)
        elif qtype == "fill":
            ok = _fill_blank_by_snapshot(i, str(answer or ""))
        else:
            log(f"第{i}题为简答，留空（essay 不提交）")
        if ok:
            filled += 1
        offset += len(opts)
    return filled


def _fill_blank_by_snapshot(question_no: int, text: str) -> bool:
    """填空题：经快照 textbox ref 填写（首个文本框）。"""
    if not text:
        return False
    try:
        snap = pw_snapshot()
    except Exception as e:
        log(f"填空题快照失败：{e}", "WARN")
        return False
    m = re.search(r"- (?:textbox|editable)[^\n]*\[ref=(e\d+)\]", snap)
    if not m:
        log(f"第{question_no}题未找到可填文本框，留空", "WARN")
        return False
    try:
        from core.browser.engine import pw_fill
        pw_fill(m.group(1), text)
        human_delay(0.5, 0.1)
        return True
    except Exception as e:
        log(f"填空题填写失败：{e}", "WARN")
        return False


def submit_exam() -> bool:
    """提交测验（快照文本定位提交/交卷按钮 + 确认弹窗）。"""
    snap = pw_snapshot()
    ref = (find_ref_by_text(snap, "提交")
           or find_ref_by_text(snap, "交卷")
           or find_ref_by_text(snap, "确定提交"))
    if not ref:
        log("未找到提交按钮", "ERROR")
        return False
    pw_click(ref)
    human_delay(2.0, 0.25)
    confirm_snap = pw_snapshot()
    confirm_ref = find_ref_by_text(confirm_snap, "确定") or find_ref_by_text(confirm_snap, "确认")
    if confirm_ref:
        pw_click(confirm_ref)
        human_delay(1.0, 0.3)
    return True


# ── 求解器主体 ──────────────────────────────────────────────────────


class ZhihuishuQuizSolver:
    """完成一门课的章节测验/作业（章树真实点击 → 逐节抽取/AI/填答/提交）。"""

    def __init__(self, course: dict, dry_run: bool = False,
                 grade_only: bool = False):
        self.course = course
        self.recruit_id = course["recruitId"]
        self.course_id = course["courseId"]
        self.dry_run = dry_run
        self.grade_only = grade_only
        self.stats = {"sections": 0, "solved": 0, "skipped": 0, "failed": 0}

    def run(self) -> bool:
        name = self.course.get("name", "?")
        if self.dry_run:
            log(f"[ZHS-Quiz] DRY RUN：{name} 将进行章节测验求解（未导航未提交）")
            return True

        log(f"[ZHS-Quiz] 开始处理：{name}")
        pw_goto(build_study_url(self.recruit_id, self.course_id))
        human_delay(4.0, 0.3)
        scroll_load_chapter_tree()

        sections = self._pending_quiz_sections()
        if not sections:
            log(f"[ZHS-Quiz] {name} 无章节测验")
            return True
        log(f"[ZHS-Quiz] 待处理测验 {len(sections)} 节")

        for i, sec in enumerate(sections, 1):
            check_signals()
            log(f"[ZHS-Quiz] ({i}/{len(sections)}) {sec['name']}")
            self.stats["sections"] += 1
            if self._solve_section(sec["name"]):
                self.stats["solved"] += 1
            else:
                self.stats["failed"] += 1
            # 真实提交之间的拟人间隔（模拟运行/未提交则跳过）
            if i < len(sections) and not (self.grade_only or self.dry_run):
                pause = random.uniform(*_SUBMIT_PACING_S)
                log(f"  提交间拟人间隔 {pause:.0f}s")
                time.sleep(pause)
        log(f"[ZHS-Quiz] {name} 完成：{self.stats}")
        return self.stats["failed"] == 0

    def _pending_quiz_sections(self) -> list:
        """从章节树提取测验入口（li.chapter-test，含文本用于真实点击定位）。"""
        js = """
async (page) => {
  const r = await page.evaluate(() => {
    const items = [];
    document.querySelectorAll('ul.list li.chapter-test').forEach((li, i) => {
      const el = li.querySelector('.name') || li;
      items.push({idx: i, name: (el.getAttribute('title') || el.innerText || '').trim()});
    });
    return JSON.stringify({items});
  });
  return r;
}
"""
        try:
            data = _run_json(js, timeout=20)
        except Exception as e:
            log(f"测验入口读取失败：{e}", "ERROR")
            return []
        return [s for s in data.get("items", []) if s.get("name")]

    def _solve_section(self, section_name: str) -> bool:
        # 1. 真实点击章测入口（text 选择器唯一匹配小节名）
        try:
            from core.browser.engine import pw
            pw("click", f"text={section_name}", timeout=10)
        except Exception as e:
            log(f"点击测验入口「{section_name}」失败：{e}", "WARN")
            return False
        human_delay(4.0, 0.5)

        # 2. 抽取题面（等待渲染；超时按无内容/已交卷处理）
        questions_raw = []
        for _ in range(3):
            questions_raw = extract_exam_questions()
            if questions_raw:
                break
            human_delay(2.0, 0.3)
        if not questions_raw:
            snap = ""
            try:
                snap = pw_snapshot()
            except Exception:
                pass
            score = parse_score(snap)
            if score is not None:
                log(f"「{section_name}」已交卷（得分 {score}），跳过")
                self.stats["skipped"] += 1
            else:
                log(f"「{section_name}」未发现题面（可能为非测验内容），跳过", "WARN")
                self.stats["skipped"] += 1
            self._back_to_tree()
            return True

        questions = []
        for q in questions_raw:
            questions.append({
                "type": detect_question_type(q.get("typeText", ""),
                                             len(q.get("options", []))),
                "stem": q.get("stem", ""),
                "options": q.get("options", []),
            })

        # 3. AI 作答（文本优先；题干为空走截图兜底）
        if all(q["stem"] for q in questions):
            from core.ai.router import ai_solve_quiz
            answers = ai_solve_quiz(build_ai_questions(questions),
                                    self.course.get("name", ""),
                                    section_name)
        else:
            answers = self._solve_by_screenshot(section_name)

        # 4. 填答
        filled = fill_answers(questions, answers or [])
        log(f"「{section_name}」填答 {filled}/{len(questions)} 题")

        # 5. 提交（grade_only 绝不提交——人工接管）
        if self.grade_only:
            log(f"[ZHS-Quiz] 模拟运行：「{section_name}」已填答未提交"
                f"（{self.course.get('name', '')}），请人工检查后接管")
            self._back_to_tree()
            return True

        if not submit_exam():
            log(f"「{section_name}」提交失败", "ERROR")
            self._back_to_tree()
            return False
        human_delay(2.5, 0.5)
        try:
            score = parse_score(pw_snapshot())
            log(f"「{section_name}」已提交{f'（得分 {score}）' if score is not None else ''}")
        except Exception:
            log(f"「{section_name}」已提交")
        self._back_to_tree()
        return True

    def _solve_by_screenshot(self, section_name: str) -> list:
        """截图兜底：整页截图 → AI 视觉作答（题干反爬/富文本时）。"""
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        path = str(TMP_DIR / "zhs_quiz_fallback.png")
        if not _fullpage_screenshot(path):
            return []
        try:
            from core.ai.router import ai_solve_quiz_image
            answers = ai_solve_quiz_image([path],
                                          self.course.get("name", ""),
                                          section_name)
            log(f"「{section_name}」截图兜底作答 {len(answers)} 题")
            return answers
        except Exception as e:
            log(f"截图兜底作答失败：{e}", "WARN")
            return []

    def _back_to_tree(self) -> None:
        """返回章节树（重新导航学习页，真实导航）。"""
        pw_goto(build_study_url(self.recruit_id, self.course_id))
        human_delay(3.0, 0.4)
        scroll_load_chapter_tree()
