"""智慧树课程与章节扫描（DOM 解析，无需签名接口）。

页面与选择器依据 2026-09-12 实地勘察（调研报告附录 B），全部经
「DOM + 视觉」交叉确认或标 🔶 待有头实测复核：
    课程列表  onlineweb.zhihuishu.com/onlinestuh5
        卡片   dl > dt > .item-left-course（.courseName/.teacherName/.processNum）
        ID     卡片内 a[href*=recruitId] 链接的 query 参数
    学习页    studyvideoh5.zhihuishu.com/stuStudy?recruitAndCourseId=…
        章节树 ul.list 下 li（chapter / video / chapter-test）
"""

import json

from core.logging_setup import log
from core.browser.engine import pw_snapshot, pw_click
from core.browser.js_runner import _run_js_file, pw_extract_result
from core.session import _get_active_session
from core.utils import human_delay, find_ref_by_text

from platforms.zhihuishu.constants import COURSE_LIST_URL, build_study_url

# M2 范围：只扫共享课；翻转课/兴趣课/智慧课程留枚举（调研报告 Q2）
COURSE_KIND_SHARED = "shared"


_COURSES_JS = """
async (page) => {
  const r = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('dl')]
      .filter(dl => dl.querySelector('.courseName'));
    return JSON.stringify(cards.map(dl => {
      let recruitId = null, courseId = null;
      const link = dl.querySelector('a[href*="recruitId"]');
      if (link) {
        try {
          const u = new URL(link.href, location.origin);
          recruitId = u.searchParams.get('recruitId');
          courseId = u.searchParams.get('courseId');
        } catch (e) {}
      }
      return {
        name: (dl.querySelector('.courseName') || {}).innerText?.trim() || '',
        teacher: (dl.querySelector('.teacherName') || {}).innerText
                  ?.replace(/\\s+/g, ' ').trim() || '',
        progress: (dl.querySelector('.processNum') || {}).innerText?.trim() || '',
        recruitId, courseId,
      };
    }).filter(c => c.name));
  });
  return r;
}
"""

_SECTIONS_JS = """
async (page) => {
  const r = await page.evaluate(() => {
    const ul = document.querySelector('ul.list');
    if (!ul) return JSON.stringify({error: 'NO_TREE'});
    const items = [];
    ul.querySelectorAll('li').forEach(li => {
      const cls = li.className || '';
      if (cls.includes('chapter') && !cls.includes('chapter-test')) {
        items.push({
          kind: 'chapter',
          num: (li.querySelector('.catalogue_title3 b') || {}).innerText?.trim() || '',
          name: (li.querySelector('span.catalogue_title') || {})
                  .getAttribute?.('title') || (li.querySelector('span.catalogue_title') || {}).innerText?.trim() || '',
        });
      } else if (cls.includes('chapter-test')) {
        items.push({
          kind: 'quiz',
          name: (li.querySelector('.name') || {}).innerText?.trim() || '平时测试',
        });
      } else if (cls.includes('video')) {
        const title = li.querySelector('span.catalogue_title');
        const durMatch = (li.innerText || '').match(/(\\d{1,2}:\\d{2}:\\d{2})/);
        items.push({
          kind: 'video',
          num: (li.querySelector('b.hour') || {}).innerText?.trim() || '',
          name: title ? (title.getAttribute('title') || title.innerText.trim()) : '',
          duration: durMatch ? durMatch[1] : '',
          current: cls.includes('current_play'),
          finished: !!li.querySelector('.time_icofinish, .icon-finish'),
        });
      }
    });
    return JSON.stringify({items});
  });
  return r;
}
"""


def _run_json(js: str, timeout: int = 20):
    raw = _run_js_file(js, timeout=timeout)
    return json.loads(pw_extract_result(raw) or raw)


def scan_courses() -> list[dict]:
    """Scan the shared-course list on the student home page.

    Returns [{name, teacher, progress, recruitId, courseId, kind}].
    """
    from core.browser.engine import pw_goto
    pw_goto(COURSE_LIST_URL)
    human_delay(3.5, 0.25)
    try:
        rows = _run_json(_COURSES_JS, timeout=30)
    except Exception as e:
        log(f"课程列表解析失败：{e}", "ERROR")
        return []
    courses = []
    for r in rows:
        if not r.get("recruitId") or not r.get("courseId"):
            log(f"课程卡片缺 ID，跳过：{r.get('name', '?')}", "WARN")
            continue
        courses.append({
            "name": r["name"],
            "teacher": r.get("teacher", ""),
            "progress": r.get("progress", ""),
            "recruitId": r["recruitId"],
            "courseId": r["courseId"],
            "kind": COURSE_KIND_SHARED,
        })
    log(f"智慧树课程扫描完成：{len(courses)} 门共享课")
    return courses


def _build_tree(items: list[dict]) -> dict:
    """Assemble the chapter tree from flat li items (pure, testable)."""
    chapters: list[dict] = []
    quiz_sections: list[str] = []
    current = None
    for it in items:
        kind = it.get("kind")
        if kind == "chapter":
            current = {"num": it.get("num", ""), "name": it.get("name", ""),
                       "sections": []}
            chapters.append(current)
        elif kind == "video":
            if current is None:
                current = {"num": "", "name": "", "sections": []}
                chapters.append(current)
            current["sections"].append({
                "kind": "video",
                "num": it.get("num", ""),
                "name": it.get("name", ""),
                "duration": it.get("duration", ""),
                "finished": bool(it.get("finished")),
            })
        elif kind == "quiz":
            host = current["name"] if current else ""
            quiz_sections.append(host or "未分组")
            if current:
                current["sections"].append({
                    "kind": "quiz",
                    "num": "",
                    "name": it.get("name", "平时测试"),
                    "duration": "",
                    "finished": False,
                })
    return {"chapters": chapters, "quiz_sections": quiz_sections}


def scan_course_sections(recruit_id: str, course_id: str) -> dict | None:
    """Open the study page and parse the chapter tree.

    Returns {chapters: [{num, name, sections: [{kind, num, name, duration,
    finished}]}], quiz_sections: [章节名]}；解析失败返回 None。
    """
    from core.browser.engine import pw_goto
    url = build_study_url(recruit_id, course_id)
    pw_goto(url)
    human_delay(4.0, 0.3)

    # 学习页可能弹「课程提醒」（公众号绑定）——关闭后继续
    try:
        snap = pw_snapshot()
        later = find_ref_by_text(snap, "下次再说")
        if later:
            pw_click(later)
            human_delay(0.8, 0.1)
    except Exception:
        pass

    try:
        data = _run_json(_SECTIONS_JS, timeout=30)
    except Exception as e:
        log(f"章节树解析失败：{e}", "ERROR")
        return None
    if not isinstance(data, dict) or data.get("error"):
        log(f"章节树不可用：{data}", "ERROR")
        return None

    tree = _build_tree(data.get("items", []))
    total = sum(len(c["sections"]) for c in tree["chapters"])
    log(f"章节树解析完成：{len(tree['chapters'])} 章 / {total} 小节"
        f"（含 {len(tree['quiz_sections'])} 个章测入口）")
    return tree
