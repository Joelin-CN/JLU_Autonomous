"""智慧树视频章节完成器（M3）—— D6 决策：仅 1.0 倍速真实播放。

策略红线（ADR D6，2026-09-12 用户决策）：
    - 不触碰倍速菜单（保持站点默认 1.0x）
    - 静音/播放/下一节全部走站点自身控件的**真实点击**（pw click）
    - 观察用 JS 仅只读（paused / currentTime / 元素存在性），
      禁止 evaluate 驱动 video.play() 等媒体操作
    - 轮询节奏带随机抖动（4–7s），节间加人味停顿
    - 不伪造心跳/不调用上报接口——播放器自行上报
    - 窗口不得最小化（由运行环境保证，见验证清单）

弹题处理（视频进度被弹题阻塞时）：采用 406653 油猴脚本沉淀的
「试选→页面在 .answer span 暴露正确答案→改选」纯 DOM 技巧，
全部为真实点击；M4 将接入 AI 路由升级。
"""

import json
import random
import time

from core.config import cfg
from core.logging_setup import log, ticket
from core.session import _get_active_session
from core.browser.engine import pw, pw_snapshot
from core.browser.js_runner import _run_js_file, pw_extract_result
from core.utils import human_delay

from platforms.zhihuishu.constants import build_study_url

# 观看轮询节奏（秒，带抖动）
_WATCH_INTERVAL = (4.0, 7.0)
# 单视频最长观看时间上限（防挂死）：按需可调
_MAX_WATCH_SECONDS = 4 * 3600
# 连续异常播放状态（暂停却点不动）达到阈值则跳过该节
_STALLED_LIMIT = 6


def _run_json(js: str, timeout: int = 20):
    raw = _run_js_file(js, timeout=timeout)
    data = json.loads(pw_extract_result(raw) or raw)
    if isinstance(data, str):
        data = json.loads(data)
    return data


def _read_video_state() -> dict:
    """只读探测播放器与页面状态（不驱动任何媒体）。

    可见性判定必须 fixed-aware：弹题层 .dialog-test 与锁课 mask 都是
    fixed 定位，offsetParent 恒为 null，不能用 offsetParent 判可见。
    """
    js = """
async (page) => {
  const r = await page.evaluate(() => {
    const visible = el => {
      if (!el) return false;
      const cs = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return cs.display !== 'none' && cs.visibility !== 'hidden' && rect.width > 0;
    };
    const v = document.querySelector('video');
    const dlg = document.querySelector('.el-dialog__wrapper.dialog-test')
             || document.querySelector('.el-dialog');
    const lock = document.querySelector('.video-study .dialog .mask');
    return JSON.stringify({
      hasVideo: !!v,
      paused: v ? v.paused : null,
      currentTime: v ? v.currentTime : null,
      duration: v ? v.duration : null,
      ended: v ? v.ended : null,
      dialogVisible: visible(dlg),
      lockVisible: visible(lock),
      url: location.href,
    });
  });
  return r;
}
"""
    try:
        return _run_json(js, timeout=15)
    except Exception as e:
        log(f"播放状态读取失败：{e}", "WARN")
        return {}


def _click(selector: str, what: str) -> bool:
    """真实点击站点控件（唯一 CSS 选择器）。"""
    try:
        pw("click", selector, timeout=cfg("timeouts.click_action", 10))
        return True
    except Exception as e:
        log(f"点击 {what}（{selector}）失败：{e}", "WARN")
        return False


def _dismiss_blocking_dialogs() -> bool:
    """清扫阻挡播放的非答题弹窗（学前必读 / 课程提醒）。

    实测：这两种弹窗会在进入学习页与播放中途反复出现（"下次再说"仅
    当次有效）；不清扫会拦截一切对播放区的点击。返回是否清扫了弹窗。
    """
    cleared = False
    # 课程提醒（dialog-warn）：点「下次再说」
    warn_js = """
async (page) => {
  const r = await page.evaluate(() => {
    const el = document.querySelector('.el-dialog__wrapper.dialog-warn');
    if (!el) return JSON.stringify({visible: false});
    const cs = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return JSON.stringify({visible: cs.display !== 'none' && rect.width > 0});
  });
  return r;
}
"""
    try:
        if _run_json(warn_js, timeout=10).get("visible"):
            log("检测到「课程提醒」弹窗，点「下次再说」...")
            _click(".dialog-warn .talk-later-btn", "课程提醒-下次再说")
            human_delay(1.0, 0.2)
            cleared = True
    except Exception:
        pass

    # 学前必读（dialog-read）：点右上角 X（含重试验证）
    if _dismiss_pre_study_dialog():
        cleared = True
    return cleared


def _dismiss_pre_study_dialog() -> bool:
    """关掉「学前必读」弹窗（关闭方式是右上角 X，需重试验证）。"""
    probe = """
async (page) => {
  const r = await page.evaluate(() => {
    const el = document.querySelector('.preschool-Mustread-div');
    if (!el) return JSON.stringify({visible: false});
    const cs = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const visible = cs.display !== 'none' && cs.visibility !== 'hidden'
                    && rect.height > 0;
    return JSON.stringify({visible});
  });
  return r;
}
"""

    def _dialog_visible() -> bool:
        try:
            return bool(_run_json(probe, timeout=10).get("visible"))
        except Exception:
            return False

    if not _dialog_visible():
        return False
    log("检测到「学前必读」弹窗，点击右上角关闭...")
    for attempt in range(3):
        _click(".dialog-read .iconguanbi", f"学前必读-关闭X(第{attempt + 1}次)")
        human_delay(1.2, 0.2)
        if not _dialog_visible():
            log("「学前必读」弹窗已关闭")
            return True
    log("「学前必读」弹窗多次关闭失败", "WARN")
    return False


def _ensure_muted() -> None:
    """静音（仅当当前有声时点击；音量钮是切换型控件，盲点会开声）。"""
    probe = """
async (page) => {
  const r = await page.evaluate(() => {
    const box = document.querySelector('.volumeBox');
    return JSON.stringify({muted: !!((box && box.className) || '').includes('volumeNone')});
  });
  return r;
}
"""
    try:
        st = _run_json(probe, timeout=10)
        if st.get("muted"):
            return
    except Exception:
        pass
    _click(".volumeBox .volumeIcon", "静音")


def scroll_load_chapter_tree(max_rounds: int = 20) -> int:
    """滚动章节树直到元素数稳定（el-scrollbar 懒加载补全）。"""
    js_count = """
async (page) => {
  const r = await page.evaluate(() => {
    const wrap = document.querySelector('.chapterScrollbar .el-scrollbar__wrap');
    const n = document.querySelectorAll('ul.list li').length;
    if (wrap) wrap.scrollTop += wrap.clientHeight * 0.8;
    return JSON.stringify({n});
  });
  return r;
}
"""
    last = -1
    stable = 0
    for _ in range(max_rounds):
        try:
            state = _run_json(js_count, timeout=15)
        except Exception:
            break
        n = state.get("n", 0)
        if n == last:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
            last = n
        time.sleep(0.8)
    log(f"章节树滚动加载完成：{last} 个节点")
    return last


def _handle_popup_quiz() -> bool:
    """弹题处理（2026-09-12 全链路实测验证）。

    链路：试选第一项 → 页面在 .answer 揭示「正确答案：B」→ 按字母点
    对应项（结构实测为 [A文, A母, B文, B母, ...] 交替，字母 L 的文本项
    在 nth=L*2）→ 关闭 footer 按钮。全部真实点击；答题后由调用方恢复播放。
    """
    probe = """
async (page) => {
  const r = await page.evaluate(() => {
    const dlg = document.querySelector('.el-dialog__wrapper.dialog-test')
             || document.querySelector('.el-dialog');
    const visible = el => {
      if (!el) return false;
      const cs = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return cs.display !== 'none' && cs.visibility !== 'hidden' && rect.width > 0;
    };
    if (!visible(dlg)) return JSON.stringify({has: false});
    const title = (dlg.querySelector('.title-tit, .topic-title') || {}).innerText || '';
    const answer = (dlg.querySelector('.answer') || {}).innerText || '';
    const optCount = dlg.querySelectorAll('.topic-list .topic-item, .topic-option-item').length;
    return JSON.stringify({has: true, title: title.trim().slice(0, 40), answer: answer.trim(), optCount});
  });
  return r;
}
"""
    try:
        st = _run_json(probe, timeout=15)
    except Exception:
        return False
    if not st.get("has"):
        return False
    log(f"检测到弹题：{st.get('title', '')[:30]}（{st.get('optCount', 0)} 节点）")

    # 1) 试选第一项（触发答案揭示）
    _click(".dialog-test .topic-list .topic-item >> nth=0", "弹题试选")
    human_delay(1.2, 0.2)

    # 2) 读答案（如「正确答案：B」或「正确答案：A,C」）
    try:
        st2 = _run_json(probe, timeout=15)
        raw = st2.get("answer", "")
    except Exception:
        raw = ""
    import re
    m = re.search(r"正确答案[：:]\s*([A-Z,，\s]+)", raw)
    letters = [c for c in (m.group(1) if m else "") if "A" <= c <= "Z"]
    log(f"弹题答案揭示：{raw[:20] or '未揭示'} → 选 {letters or '保持试选'}")

    # 3) 按字母点击对应文本项（nth = 字母序*2）
    for letter in letters or []:
        nth = (ord(letter) - ord("A")) * 2
        _click(f".dialog-test .topic-list .topic-item >> nth={nth}",
               f"弹题选项{letter}")
        human_delay(0.7, 0.15)

    # 4) 关闭弹题
    human_delay(0.8, 0.15)
    _click(".dialog-test .el-dialog__footer .btn", "弹题关闭")
    human_delay(1.2, 0.2)
    return True


def _report_lock_ticket(course_name: str) -> None:
    ticket({
        "id": f"zhihuishu-locked-{course_name}",
        "type": "warning",
        "title": "智慧树课程锁定",
        "message": f"课程「{course_name}」被平台判定异常学习行为锁定，已跳过；"
                   f"请到 onlineh5.zhihuishu.com/subPage.html#/student/exceptionRecordList 申诉",
        "resolved": False,
    })


class ZhihuishuVideoBot:
    """按 D6 策略完成一门课的视频章节（原速真实播放）。"""

    def __init__(self, course: dict):
        self.course = course
        self.recruit_id = course["recruitId"]
        self.course_id = course["courseId"]

    def run(self) -> bool:
        from core.browser.engine import pw_goto
        name = self.course.get("name", "?")
        log(f"[ZHS-Video] 开始处理：{name}（原速真实播放策略）")
        pw_goto(build_study_url(self.recruit_id, self.course_id))
        human_delay(4.0, 0.3)

        # 锁课检测（M2 实测：.video-study>.dialog 全屏 mask）
        state = _read_video_state()
        if state.get("lockVisible"):
            log(f"课程「{name}」已被锁定，跳过", "ERROR")
            _report_lock_ticket(name)
            return False

        scroll_load_chapter_tree()

        sections = self._pending_sections()
        total = len(sections)
        if not total:
            log(f"[ZHS-Video] {name} 无待完成视频节")
            return True
        log(f"[ZHS-Video] 待完成 {total} 节，逐节真实播放")

        for i, sec in enumerate(sections, 1):
            log(f"[ZHS-Video] ({i}/{total}) {sec['num']} {sec['name']}")
            self._play_section(sec)
            human_delay(2.5, 1.0)   # 节间人味停顿
        return True

    def _pending_sections(self) -> list:
        """从当前章节树提取未完成的视频节（含文本用于真实点击定位）。"""
        js = """
async (page) => {
  const r = await page.evaluate(() => {
    const items = [];
    document.querySelectorAll('ul.list li').forEach((li, i) => {
      const cls = li.className || '';
      if (!cls.includes('video')) return;
      const title = li.querySelector('span.catalogue_title');
      const name = title ? (title.getAttribute('title') || title.innerText.trim()) : '';
      const finished = !!li.querySelector('.time_icofinish, .icon-finish');
      const num = (li.querySelector('b.hour') || {}).innerText?.trim() || '';
      items.push({idx: i, num, name, finished});
    });
    return JSON.stringify({items});
  });
  return r;
}
"""
        try:
            data = _run_json(js, timeout=20)
        except Exception as e:
            log(f"章节树读取失败：{e}", "ERROR")
            return []
        return [s for s in data.get("items", []) if not s.get("finished")]

    def _play_section(self, sec: dict) -> None:
        # 1. 真实点击小节（text 选择器唯一匹配小节名）
        if sec.get("name"):
            _click(f"text={sec['name']}", f"小节 {sec['num']}")
            human_delay(2.0, 0.4)

        # 2. 清扫阻挡弹窗（学前必读 / 课程提醒，播放中途也会再弹）
        _dismiss_blocking_dialogs()
        human_delay(0.5, 0.1)

        # 3. 静音（站点自身音量控件的真实点击；类人且降低环境干扰）
        _ensure_muted()
        human_delay(0.4, 0.1)

        # 4. 直接点击视频画面开始播放（实测：.bigPlayButton 需 hover 才渲染，
        #    且 CLI 单命令模式下悬停态跨命令不保持；videoArea 单击即切换）
        _click(".videoArea", "播放(点击画面)")

        # 5. 观看循环：只读轮询 + 真实点击恢复
        self._watch_loop(sec)

    def _watch_loop(self, sec: dict) -> None:
        stalled = 0
        deadline = time.time() + _MAX_WATCH_SECONDS
        last_t = 0.0
        while time.time() < deadline:
            time.sleep(random.uniform(*_WATCH_INTERVAL))  # 4–7s 人味轮询
            st = _read_video_state()

            if st.get("lockVisible"):
                _report_lock_ticket(self.course.get("name", "?"))
                return

            # 弹题优先处理（它会暂停视频）
            if st.get("dialogVisible"):
                _handle_popup_quiz()
                human_delay(1.0, 0.2)
                _click(".videoArea", "弹题后恢复播放")
                continue

            if not st.get("hasVideo"):
                stalled += 1
                if stalled > _STALLED_LIMIT:
                    log("找不到 video 元素，跳过本节", "WARN")
                    return
                continue

            cur = float(st.get("currentTime") or 0.0)
            dur = float(st.get("duration") or 0.0)

            if st.get("ended") or (dur > 0 and cur >= dur - 2.0):
                log(f"  本节完成（{cur:.0f}/{dur:.0f}s）")
                return

            if _dismiss_blocking_dialogs():
                stalled = 0
                continue

            if st.get("paused"):
                # 未到结尾却暂停：可能被站点防挂机暂停，真实点击恢复
                stalled += 1
                if stalled > _STALLED_LIMIT:
                    log("多次恢复播放无效，跳过本节", "WARN")
                    return
                human_delay(1.5, 0.5)
                _click(".videoArea", "恢复播放(点击画面)")
                continue

            if cur <= last_t + 0.1 and not st.get("paused"):
                # 进度不走且非暂停（假播放/后台节流）——重试一次点击
                stalled += 1
                if stalled > _STALLED_LIMIT:
                    log("播放进度停滞，跳过本节", "WARN")
                    return
            else:
                stalled = 0
            last_t = cur

        log("观看超时上限，跳到下一节", "WARN")

    def next_section(self) -> None:
        """真实点击下一节按钮。"""
        _click("#nextBtn", "下一节")
        human_delay(2.0, 0.4)
