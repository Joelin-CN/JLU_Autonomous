"""智慧树章节测验/作业求解器（M4）——抽取 → AI 作答 → 填答 → 提交。

架构对齐超星 ``platforms/chaoxing/solvers/quiz/``；AI 路由复用
``core.ai.router``（配置同源 ``chaoxing_config.json``）。

真机 DOM 事实（2026-09-13 探针实测，data/output/discovered_courses_* 与
``docs/reports/analysis/ZHIHUISHU_ANALYSIS_2026-09-12.md`` §4 互补）：
    - 点击章节树 ``li.chapter-test`` 在**新标签页**打开试卷
      ``onlineexamh5new.zhihuishu.com/stuExamWeb.html#/webExamList/dohomework/...``；
      学习页本身不加载任何题面。
    - 试卷页**单题展示**：``.examPaper_subject`` 全量在 DOM，但仅当前题可见；
      「下一题」翻页并保存答案。
    - 题干异步/加密渲染：``.subject_describe`` 的 DOM 文本为空、屏幕上可见
      （截图可读）→ 题干走**截图→AI 视觉**；选项文本在 DOM 明文
      （``.nodeLab``：字母 span + 隐藏 radio + ``.examquestions-answer`` 文本）。
    - 选项顺序随机排列（页面明示「以选项内容为准」）。

反自动化红线（分析报告 Q5 / D6 同源纪律）：
    - 只用真实点击（locator click，可信事件）；JS 仅只读取值/截图
    - 真实提交之间 60–120s 随机节奏（dry_run / grade_only 跳过）
    - grade_only（模拟运行）：完整导航→抽取→AI→填答，**绝不提交/暂存**

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
from core.browser.engine import pw_goto
from core.browser.js_runner import _run_js_file, pw_extract_result
from core.utils import human_delay

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


def judge_answer_text(answer) -> str:
    """判断题答案 → 选项文本匹配键：正确/对 → '对'，错误/错 → '错'；'' = 无法解析。"""
    text = str(answer if not isinstance(answer, list) else (answer[0] if answer else ""))
    if re.search(r"正确|对|√|true", text, re.IGNORECASE):
        return "对"
    if re.search(r"错误|错|×|false", text, re.IGNORECASE):
        return "错"
    return ""


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
    """把抽取的题块组装为 AI 路由入参。

    ``core.ai.prompts.format_quiz_text_prompt`` 消费 ``{index, question,
    options}`` 结构（question 为题干、options 为已带字母前缀的选项行）——
    不是整段 text，否则题干进不了 prompt（DeepSeek 实测返回空数组）。
    """
    out = []
    for i, q in enumerate(questions, 1):
        options = [f"{chr(65 + j)}. {opt}"
                   for j, opt in enumerate(q.get("options", []))]
        out.append({
            "index": i,
            "question": f"【{q.get('type', 'single')}】{q.get('stem', '').strip()}",
            "options": options,
        })
    return out


def parse_reveal_letters(raw: str) -> list:
    """弹题揭示文本 → 字母表（如「正确答案：A,C」→ ['A','C']）。"""
    m = re.search(r"正确答案[：:]\s*([A-Z,，\s]+)", raw or "")
    return [c for c in (m.group(1) if m else "") if "A" <= c <= "Z"]


def map_answer_to_letters(answer, qtype: str, option_letters: list,
                          option_texts: list) -> list:
    """把 AI 答案映射到当前题的选项字母（选项随机排列，以内容/可见字母为准）。

    - single/multi：直接取答案字母，并与实际存在的字母求交
    - judge：按「对/错」文本匹配选项内容再取其字母
    """
    if qtype == "judge":
        key = judge_answer_text(answer)
        if not key:
            return []
        for letter, text in zip(option_letters, option_texts):
            if key in text or text in key:
                return [letter]
        return []
    letters = [l for l in parse_answer_letters(answer) if l in option_letters]
    return letters


# ── 浏览器探针（JS 仅只读；点击一律 locator 真实事件）────────────────


def _run_json(js: str, timeout: int = 20):
    raw = _run_js_file(js, timeout=timeout)
    try:
        data = json.loads(pw_extract_result(raw) or raw)
        if isinstance(data, str):
            data = json.loads(data)
        return data
    except Exception:
        # CLI 会把 Playwright 错误（如 locator 超时）原样输出为非 JSON 文本——
        # 带出真实原因，别让「Expecting value: char 0」掩盖 locator 超时
        lines = (raw or "").strip().splitlines()
        excerpt = lines[-1][:200] if lines else "<empty>"
        raise RuntimeError(f"exam op 非法输出: {excerpt}")


def _exam_op(body: str, timeout: int = 30) -> dict:
    """在试卷新标签页上执行操作（page 上下文自动定位 stuExamWeb 页）。"""
    js = (
        "async (page) => {\n"
        "  const pages = page.context().pages()"
        ".filter(p => p.url().includes('stuExamWeb'));\n"
        "  const exam = pages[pages.length - 1];\n"  # 最新一张（防陈旧标签）
        "  if (!exam) return JSON.stringify({error: 'no-exam-page'});\n"
        "  await exam.bringToFront();\n"
        + body +
        "\n}"
    )
    return _run_json(js, timeout=timeout)


def wait_for_exam_page(timeout_s: float = 15.0) -> bool:
    """等待章测新标签页出现（点击入口后轮询）。"""
    deadline = time.time() + timeout_s
    probe = ("async (page) => {\n"
             "  const ok = page.context().pages()"
             ".some(p => p.url().includes('stuExamWeb'));\n"
             "  return JSON.stringify({ok});\n"
             "}")
    while time.time() < deadline:
        try:
            if _run_json(probe, timeout=10).get("ok"):
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def exam_page_info() -> dict:
    """读试卷页概要（URL/已交卷标记/可见题）。"""
    return _exam_op(
        "  await exam.waitForTimeout(1200);\n"
        "  const r = await exam.evaluate(() => {\n"
        "    const cnt = (sel) => document.querySelectorAll(sel).length;\n"
        "    return JSON.stringify({\n"
        "      url: location.href,\n"
        "      subjects: cnt('.examPaper_subject'),\n"
        "      submitted: /已(提交|完成)|得分/.test((document.body.innerText || '').slice(0, 2000)),\n"
        "      bodyHead: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 200),\n"
        "    });\n"
        "  });\n"
        "  return r;")


def read_current_question() -> dict:
    """读当前可见题：屏幕题号 + 题型文本 + 选项（字母/文本）。"""
    return _exam_op(
        "  await exam.waitForTimeout(1500);\n"
        "  const r = await exam.evaluate(() => {\n"
        "    const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();\n"
        "    const vis = [...document.querySelectorAll('.examPaper_subject')].find(s => {\n"
        "      const cs = getComputedStyle(s); const rect = s.getBoundingClientRect();\n"
        "      return cs.display !== 'none' && rect.height > 0;\n"
        "    });\n"
        "    if (!vis) return JSON.stringify({noVisible: true});\n"
        "    const typeEl = vis.querySelector('.subject_type_describe');\n"
        "    const numEl = vis.querySelector('.subject_num span');\n"
        "    const opts = [...vis.querySelectorAll('.nodeLab')].map(n => {\n"
        "      const letter = clean((n.querySelector('span.mr10') || {}).textContent).replace('.', '');\n"
        "      const text = clean((n.querySelector('.examquestions-answer') || n).textContent);\n"
        "      return {letter: letter.slice(0, 2), text: text.slice(0, 100)};\n"
        "    });\n"
        "    return JSON.stringify({\n"
        "      num: clean(numEl ? numEl.textContent : '').replace('.', ''),\n"
        "      typeText: clean(typeEl ? typeEl.textContent : ''),\n"
        "      stemText: clean((vis.querySelector('.subject_describe') || {}).textContent).slice(0, 200),\n"
        "      options: opts,\n"
        "    });\n"
        "  });\n"
        "  return r;")


def screenshot_current_question(path: str) -> bool:
    """截当前题整块（题干加密渲染，截图供 AI 视觉作答；JS 仅截图不改状态）。"""
    safe = path.replace("\\", "/").replace("'", "\\'")
    return _exam_op(
        "  const vis = exam.locator('.examPaper_subject:visible').first();\n"
        f"  await vis.screenshot({{path: '{safe}'}});\n"
        "  return JSON.stringify({ok: true});", timeout=40).get("ok", False)


def click_option_letter(letter: str) -> bool:
    """真实点击当前题指定字母的选项。

    字母 span（.mr10）文本恰为「A.」/「B.」——按它过滤再点所在 .label；
    不能用 /^A\\./ 锚定 nodeLab 文本（DOM 标签间空白让 ^ 失配 → 空集超时，
    真机第九轮实测教训）。
    """
    return _exam_op(
        "  const vis = exam.locator('.examPaper_subject:visible').first();\n"
        f"  const span = vis.locator('span.mr10').filter({{hasText: '{letter}.'}}).first();\n"
        "  const label = span.locator('xpath=ancestor::div[contains(@class, \"label\")][1]');\n"
        "  await label.click({timeout: 8000});\n"
        "  await exam.waitForTimeout(300);\n"
        "  return JSON.stringify({ok: true});").get("ok", False)


def confirm_multi_selection() -> bool:
    """多选题的「确定」提交钮（题块内）。

    真机巡检（2026-09-13 晚）发现多选（checkbox）选项点击后不点题块内
    「确定」就翻页，选择被整卷丢弃——两道多选草稿全空而单选/判断正常，
    与此机制完全吻合。无该按钮时返回 False（按无此交互处理）。
    """
    try:
        return _exam_op(
            "  const vis = exam.locator('.examPaper_subject:visible').first();\n"
            "  const btn = vis.getByRole('button', {name: /确\\s*定/}).first();\n"
            "  const n = await btn.count();\n"
            "  if (!n) return JSON.stringify({ok: false, reason: 'no-confirm-btn'});\n"
            "  await btn.click({timeout: 5000});\n"
            "  await exam.waitForTimeout(600);\n"
            "  return JSON.stringify({ok: true});", timeout=20).get("ok", False)
    except Exception:
        return False


def read_selections() -> list:
    """只读回读当前题各选项选中态（input.checked），返回已选字母表。"""
    try:
        st = _exam_op(
            "  const r = await exam.evaluate(() => {\n"
            "    const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();\n"
            "    const vis = [...document.querySelectorAll('.examPaper_subject')].find(s => {\n"
            "      const cs = getComputedStyle(s); const rect = s.getBoundingClientRect();\n"
            "      return cs.display !== 'none' && rect.height > 0;\n"
            "    });\n"
            "    if (!vis) return JSON.stringify({sel: []});\n"
            "    const sel = [...vis.querySelectorAll('.nodeLab')]\n"
            "      .filter(n => { const i = n.querySelector('input'); return i && i.checked; })\n"
            "      .map(n => clean((n.querySelector('span.mr10') || {}).textContent).replace('.', ''));\n"
            "    return JSON.stringify({sel});\n"
            "  });\n"
            "  return r;")
        return st.get("sel", [])
    except Exception:
        return []


def save_draft() -> bool:
    """点「暂存作业」持久化草稿（含末题答案；不交卷不判分）。

    站点保存机制是「点选项后点下一题才存」，末题没有下一题——grade-only
    下用暂存收尾（与逐题草稿同语义，非提交）。真实提交模式无需此步。
    """
    try:
        return _exam_op(
            "  const btn = exam.getByRole('button', {name: /暂存作业/}).first();\n"
            "  const n = await btn.count();\n"
            "  if (!n) return JSON.stringify({ok: false, reason: 'no-btn'});\n"
            "  await btn.click({timeout: 8000});\n"
            "  await exam.waitForTimeout(1500);\n"
            "  const confirm = exam.getByRole('button', {name: /确\\s*定/}).first();\n"
            "  try { if (await confirm.count()) await confirm.click({timeout: 3000}); } catch (e) {}\n"
            "  await exam.waitForTimeout(800);\n"
            "  return JSON.stringify({ok: true});", timeout=30).get("ok", False)
    except Exception as e:
        log(f"暂存作业失败：{e}", "WARN")
        return False


def click_next_question() -> bool:
    """真实点击「下一题」按钮（仅真按钮；末题按钮禁用时返回 False）。

    真机教训：text=下一题 会先命中橙色提示文案「请点【下一题】保存答案」
    （点击成功但无效果）→ 末题死循环空烧 AI。改为 getByRole('button')
    限定真按钮，并先探其可用性。
    """
    try:
        return _exam_op(
            "  const btn = exam.getByRole('button', {name: /下一题/}).first();\n"
            "  const enabled = await btn.isEnabled().catch(() => false);\n"
            "  if (!enabled) return JSON.stringify({ok: false, reason: 'disabled'});\n"
            "  await btn.click({timeout: 8000});\n"
            "  await exam.waitForTimeout(800);\n"
            "  return JSON.stringify({ok: true});").get("ok", False)
    except Exception as e:
        log(f"点击下一题失败：{e}", "WARN")
        return False


def submit_exam() -> bool:
    """真实提交试卷（「提交作业」+ 确认弹窗）。grade_only 永不调用。"""
    try:
        ok = _exam_op(
            "  await exam.locator('text=提交作业').first().click({timeout: 8000});\n"
            "  await exam.waitForTimeout(1500);\n"
            "  const confirm = exam.locator('text=确定').first();\n"
            "  try { await confirm.click({timeout: 3000}); } catch (e) {}\n"
            "  return JSON.stringify({ok: true});", timeout=40).get("ok", False)
        return ok
    except Exception as e:
        log(f"提交失败：{e}", "ERROR")
        return False


def close_exam_page() -> None:
    """关掉试卷标签页，回到学习页（真实页面操作）。"""
    try:
        _exam_op(
            "  await exam.close();\n"
            "  const study = page.context().pages()"
            ".find(p => p.url().includes('stuStudy'));\n"
            "  if (study) await study.bringToFront();\n"
            "  return JSON.stringify({ok: true});")
    except Exception as e:
        log(f"关闭试卷页失败：{e}", "WARN")


# ── 求解器主体 ──────────────────────────────────────────────────────


class ZhihuishuQuizSolver:
    """完成一门课的章节测验/作业（章树真实点击 → 逐题截图/AI/填答/提交）。"""

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
            log(f"[ZHS-Quiz] ({i}/{len(sections)}) {sec['name']}（入口 #{sec['idx']}）")
            self.stats["sections"] += 1
            try:
                status = self._solve_section(sec["idx"], sec["name"])
            except Exception as e:
                # 单节失败（如 AI 密钥缺失/网络异常）只计失败，不炸整个账号运行
                log(f"「{sec['name']}」求解异常：{e}", "ERROR")
                status = "failed"
            if status == "solved":
                self.stats["solved"] += 1
            elif status == "skipped":
                self.stats["skipped"] += 1
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
        """从章节树提取测验入口（li.chapter-test，含 nth 索引用于真实点击）。"""
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

    def _solve_section(self, idx: int, section_name: str) -> bool:
        # 1. 清扫拦截弹窗（课程提醒/学前必读会吃掉入口点击——真机实测），
        #    然后真实点击章测入口（处理器在内层 .name 上：点 li 本体不触发）
        from platforms.zhihuishu.video import _dismiss_blocking_dialogs
        _dismiss_blocking_dialogs()
        human_delay(0.5, 0.1)
        try:
            from core.browser.engine import pw
            pw("click", f"li.chapter-test .name >> nth={idx}", timeout=10)
        except Exception as e:
            log(f"点击测验入口 #{idx}「{section_name}」失败：{e}", "WARN")
            return "failed"
        human_delay(3.0, 0.5)

        # 2. 等试卷新标签页（真机实测：章测在新标签页打开 stuExamWeb）
        if not wait_for_exam_page(timeout_s=15):
            log(f"「{section_name}」未打开试卷页（可能为非测验内容），跳过", "WARN")
            return "skipped"
        info = exam_page_info()
        url = info.get("url", "")
        if "/dohomework/" not in url:
            # 列表页形态（#/webExamList?recruitId=）：v1 不深入，跳过并留档
            log(f"「{section_name}」打开的是试卷列表页而非具体试卷：{url[:80]}", "WARN")
            close_exam_page()
            return "skipped"
        if info.get("submitted") or int(info.get("subjects", 0)) < 1:
            log(f"「{section_name}」已交卷或无题面，跳过")
            close_exam_page()
            return "skipped"

        # 3. 逐题：读题型/选项（DOM 明文）→ 截图题干（加密渲染）→ AI 视觉 → 填答 → 下一题
        #    任何退出路径都留档+关试卷页，防陈旧标签让下一节错拿旧卷（第九轮教训）
        from core.ai.router import ai_solve_quiz_image
        answered, total = 0, 0
        q_no = 0
        submitted_ok = False
        last_screen_num = ""
        try:
            while True:
                q_no += 1
                check_signals()
                q = read_current_question()
                if q.get("noVisible") or not q.get("options"):
                    log(f"第 {q_no} 题不可见或无选项，停止本卷", "WARN")
                    break
                # 防死循环（第十轮教训）：点过「下一题」后屏幕题号不变 = 已到
                # 末题或翻页失效——该题首读时已作答，直接收卷，不再空烧 AI。
                screen_num = str(q.get("num", "")).strip()
                if screen_num and screen_num == last_screen_num:
                    log(f"屏幕题号停在 {screen_num}（翻页无效），按末题收卷")
                    break
                last_screen_num = screen_num
                total += 1
                opts = q["options"]
                letters = [o["letter"] for o in opts]
                texts = [o["text"] for o in opts]
                qtype = detect_question_type(q.get("typeText", ""), len(opts))

                TMP_DIR.mkdir(parents=True, exist_ok=True)
                shot = str(TMP_DIR / f"zhs_quiz_q{q_no}.png")
                answer = None
                if screenshot_current_question(shot):
                    try:
                        answers = ai_solve_quiz_image([shot], self.course.get("name", ""),
                                                      section_name)
                        answer = answers[0].get("answer") if answers else None
                    except Exception as e:
                        log(f"第 {q_no} 题 AI 作答失败：{e}", "WARN")
                else:
                    log(f"第 {q_no} 题截图失败", "WARN")

                picked = map_answer_to_letters(answer, qtype, letters, texts)
                log(f"第 {q_no} 题（{qtype}）AI={answer} → 点 {picked or '留空'}")
                if self._fill_current(qtype, picked):
                    answered += 1

                if not click_next_question():
                    log("无「下一题」（已到最后一题）")
                    break
                human_delay(2.2, 0.4)  # 等题干异步渲染

            log(f"「{section_name}」填答 {answered}/{total} 题")

            # 4. 收尾：grade_only 用「暂存作业」持久化草稿（站点保存机制是
            #    「点选项后点下一题」，末题没有下一题——不暂存则末题答案丢失，
            #    真机巡检实证）；暂存只存草稿不交卷不判分，仍属「填答不提交」。
            #    真实模式直接提交。
            if self.grade_only:
                saved = save_draft() if total > 0 else True
                log(f"[ZHS-Quiz] 模拟运行：「{section_name}」已填答"
                    f"{'并暂存草稿' if saved else '（暂存失败，末题答案可能未保存）'}未提交"
                    f"（{self.course.get('name', '')}），请人工检查后接管")
            elif total > 0 and submit_exam():
                human_delay(2.5, 0.5)
                log(f"「{section_name}」已提交")
                submitted_ok = True
            elif total > 0:
                log(f"「{section_name}」提交失败", "ERROR")
        finally:
            if total > 0:
                self._capture_paper_screenshot(section_name)
            close_exam_page()
        if self.grade_only:
            return "solved"
        return "solved" if submitted_ok else "failed"

    def _fill_current(self, qtype: str, picked: list) -> bool:
        """点击选项并校验选中态（多选先点题块内「确定」锁定），可补点一次。

        真机巡检（2026-09-13 晚）实证：多选（checkbox）不点题块内「确定」
        就翻页，选择整卷丢弃；单选/判断 radio 即点即中。校验统一回读
        input.checked——字母是每次渲染随机的，checked 才是本体。
        """
        if not picked:
            return False
        target = list(picked)
        for attempt in (1, 2):
            for letter in target:
                if not click_option_letter(letter):
                    log(f"点击选项 {letter} 失败", "WARN")
                human_delay(0.8, 0.2)
            if qtype == "multi":
                if confirm_multi_selection():
                    log("多选「确定」已点击")
                human_delay(0.5, 0.1)
            got = read_selections()
            if set(picked) <= set(got):
                return True
            missing = [l for l in picked if l not in got]
            if attempt == 1 and missing:
                log(f"选中校验缺失 {missing}（当前 {got}），补点一次", "WARN")
                target = missing  # 只补缺：多选重复点会反选
        log(f"选中校验未达标：目标 {picked} 实得 {got}", "WARN")
        return bool(got)

    def _capture_paper_screenshot(self, section_name: str) -> None:
        """留档：交卷前的答题卡/完成率整页截图（人工核对用；grade-only 关键证据）。"""
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        safe = str(TMP_DIR / "zhs_quiz_paper_final.png").replace("\\", "/").replace("'", "\\'")
        try:
            _exam_op(
                f"  await exam.screenshot({{path: '{safe}', fullPage: false}});\n"
                "  return JSON.stringify({ok: true});", timeout=40)
        except Exception:
            pass  # 留档尽力而为
