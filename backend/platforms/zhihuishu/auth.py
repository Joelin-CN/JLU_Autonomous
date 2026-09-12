"""智慧树浏览器会话与登录。

会话：zhihuishu-chrome-N，持久 profile data/chrome-profiles/zhihuishu/account-N
（与超星历史平铺路径隔离，见 core.browser.orphans.profile_dir_for_session）。

登录策略（调研结论 Q1，降级链）：
    1. profile 已带登录态（Cookie 持久化）→ 直接可用；
    2. 扫码登录（首选）：切「扫码」Tab → 截图二维码发 TICKET 工单 → 轮询
       登录跳转（知到 APP 扫码确认）；
    3. 密码登录（兜底）：JS 填表 + 真实点击提交；必触发易盾滑块 → 截图发
       工单，请用户在**有头**窗口手动完成拖拽（M2 不做自动求解，
       自动求解为独立专项 yidun_slider，见路线图）。

工程红线：提交点击必须走 pw_click（真实事件）；禁止 evaluate 驱动媒体与
monkey-patch（异常行为会锁课，见调研报告 Q5）。
"""

import base64
import os
import subprocess
import threading
import time

from core.config import cfg
from core.constants import WORKSPACE, TMP_DIR, SCREENSHOTS_DIR
from core.session import _get_active_session
from core.logging_setup import log, ticket
from core.browser.engine import (
    pw_snapshot, pw_click, pw_goto, pw,
    PlaywrightCliMissingError, ensure_cli_available,
)
from core.browser.js_runner import _run_js_file, pw_run_code_file, pw_extract_result
from core.browser.orphans import kill_orphaned_chrome, profile_dir_for_session
from core.utils import human_delay, find_ref_by_text
from core.credentials import read_accounts_file, accounts_file_path

from platforms.zhihuishu.constants import (
    LOGIN_URL, COURSE_LIST_URL,
    SESSION_PREFIX, ACCOUNTS_FILE_ENV, ACCOUNTS_FILE_NAME,
)

_LIST_LOCK = threading.Lock()

# 登录等待轮询参数
_LOGIN_POLL_INTERVAL = 3.0
_QR_LOGIN_TIMEOUT = 180.0     # 扫码等待上限（秒）
_SLIDER_LOGIN_TIMEOUT = 120.0  # 滑块人工处理等待上限（秒）


# ── 凭据 ─────────────────────────────────────────────────────────

def zhihuishu_accounts_file():
    return accounts_file_path(ACCOUNTS_FILE_ENV, ACCOUNTS_FILE_NAME)


def read_all_zhihuishu_credentials() -> list[dict]:
    return read_accounts_file(
        zhihuishu_accounts_file(),
        default_website=LOGIN_URL,
        label=ACCOUNTS_FILE_NAME,
    )


# ── 会话管理 ─────────────────────────────────────────────────────

def _session_name(account_index: int) -> str:
    return f"{SESSION_PREFIX}-{account_index}"


def _want_headed() -> bool:
    if os.environ.get("CHAOXING_HEADED", "0") == "1":
        return True
    return os.environ.get("ZHIHUISHU_HEADED", "0") == "1"


def is_zhihuishu_browser_open(session: str = None) -> bool:
    """Check whether the zhihuishu playwright-cli session is running."""
    session = session or _get_active_session()
    cli = cfg("playwright_cli", "playwright-cli.cmd")
    ensure_cli_available(cli)
    with _LIST_LOCK:
        try:
            result = subprocess.run(
                [cli, "list"],
                cwd=str(WORKSPACE), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=8, shell=False,
            )
        except subprocess.TimeoutExpired:
            log("playwright-cli list timed out — treating session as unknown",
                "WARN")
            return False
        except FileNotFoundError:
            raise PlaywrightCliMissingError(cli)
    return f"{session}:" in result.stdout or session in result.stdout


def ensure_zhihuishu_browser(account_index: int = 0) -> bool:
    """Open the persistent zhihuishu session (or reuse the running one).

    首选有头模式提示：智慧树对自动化环境指纹敏感，建议以
    ZHIHUISHU_HEADED=1 运行（扫码/滑块也需要可见窗口）。
    """
    session = _session_name(account_index)
    if is_zhihuishu_browser_open(session):
        return True

    profile = profile_dir_for_session(session, account_index)
    profile.parent.mkdir(parents=True, exist_ok=True)
    kill_orphaned_chrome(profile)

    cli = cfg("playwright_cli", "playwright-cli.cmd")
    ensure_cli_available(cli)
    log(f"Opening zhihuishu browser session ({session})...")
    cmd = [
        cli, f"-s={session}", "open", "--browser=chrome", "--persistent",
        f"--profile={profile}",
    ]
    if _want_headed():
        cmd.append("--headed")
    cmd.append("about:blank")
    try:
        result = subprocess.run(
            cmd, cwd=str(WORKSPACE), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30, shell=False,
        )
    except FileNotFoundError:
        raise PlaywrightCliMissingError(cli)
    if result.returncode != 0:
        log(f"[!] playwright-cli open failed (rc={result.returncode}): "
            f"{(result.stderr or result.stdout or '').strip()[:300]}")
    human_delay(4.0, 0.25)

    try:
        from core.session import set_active_session
        set_active_session(session)
        pw_goto(LOGIN_URL)
    except Exception as e:
        log(f"Navigate to login page failed after open: {e}", "WARN")

    try:
        title_js = ("async (page) => { await page.evaluate(() => "
                    f"{{ document.title = '智慧树 Account {account_index}'; }});"
                    " return 'ok'; }")
        _run_js_file(title_js, timeout=5)
    except Exception:
        pass

    return is_zhihuishu_browser_open(session)


def close_zhihuishu_browser(account_index: int = 0) -> bool:
    """Close the persistent session and sweep orphans for this profile."""
    session = _session_name(account_index)
    cli = cfg("playwright_cli", "playwright-cli.cmd")
    try:
        subprocess.run(
            [cli, f"-s={session}", "close"],
            cwd=str(WORKSPACE), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10, shell=False,
        )
    except Exception as e:
        log(f"Session close failed: {e}", "WARN")
        return False
    kill_orphaned_chrome(profile_dir_for_session(session, account_index))
    return True


# ── 登录态检测 ───────────────────────────────────────────────────

_LOGIN_LINK_JS = """
async (page) => {
  const r = await page.evaluate(() => {
    const body = document.body.innerText || '';
    const link = [...document.querySelectorAll('a[href*="login.zhihuishu.com"]')].find(a => (a.innerText || '').trim() === '登录');
    // bodyReady：SPA 已渲染出可判定的标志元素（登录链接 或 已登录元素）
    const ready = !!link || body.includes('身份切换') || body.includes('我的学堂');
    const loggedIn = !link && ready;
    return JSON.stringify({ loggedIn, ready, bodyReady: ready, url: location.href });
  });
  return r;
}
"""


def _probe_login_state() -> tuple[bool, str]:
    """Return (logged_in, current_url) for the active session's page.

    课程列表是 Vue SPA：goto 返回时页面可能尚未渲染完成（body 为空、
    登录链接与用户名元素都不存在），此时必须重试而不是误判为未登录。
    """
    import json as _json
    last_url = ""
    for attempt in range(4):
        raw = _run_js_file(_LOGIN_LINK_JS, timeout=15)
        try:
            data = _json.loads(pw_extract_result(raw) or raw)
            url = str(data.get("url", ""))
            last_url = url or last_url
            body_ready = data.get("bodyReady", False)
            if body_ready:
                return bool(data.get("loggedIn")), url
        except (ValueError, TypeError):
            pass
        time.sleep(1.5)
    return False, last_url


def is_logged_in_on_course_list() -> bool:
    """Navigate to the course list and check the login state."""
    pw_goto(COURSE_LIST_URL)
    human_delay(3.0, 0.25)
    try:
        ok, url = _probe_login_state()
        if "login.zhihuishu.com" in url:
            return False
        return ok
    except Exception as e:
        log(f"Login probe failed: {e}", "WARN")
        return False


# ── 工单辅助 ─────────────────────────────────────────────────────

def _screenshot_ticket(ticket_id: str, title: str, message: str,
                       timeout_note: float) -> None:
    """Screenshot the page and emit a manual-intervention ticket (QR/slider)."""
    img_b64 = ""
    try:
        shot_path = (TMP_DIR / f"{ticket_id}.png").as_posix()
        js = ("async (page) => { await page.screenshot({"
              f"path: {_js_str(shot_path)}, fullPage: false"
              "}); return 'ok'; }")
        _run_js_file(js, timeout=30)
        with open(shot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        log(f"Screenshot for ticket failed: {e}", "WARN")
    ticket({
        "id": ticket_id,
        "type": "captcha",
        "title": title,
        "message": message if img_b64
        else message + "（截图失败，请直接查看浏览器窗口）",
        "resolved": False,
        "imageBase64": img_b64,
        "timeoutSeconds": int(timeout_note),
    })


def _wait_login_redirect(timeout: float, what: str) -> bool:
    """Poll until the page leaves the login center (scan/slider completed)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(_LOGIN_POLL_INTERVAL)
        try:
            ok, url = _probe_login_state()
            # 空 URL 视为探测未就绪，绝不能当作"已跳转"（曾致扫码竞态误判）
            if url and "login.zhihuishu.com" not in url:
                log(f"{what} 完成，已跳转：{url}")
                return True
        except Exception:
            continue
    return False


# ── 登录流程 ─────────────────────────────────────────────────────

def _js_str(s: str) -> str:
    import json as _json
    return _json.dumps(s)


def _fill_password_form(account: str, password: str) -> bool:
    """Fill the login form via JS (input events); submit uses a REAL click."""
    js = ("async (page) => { const r = await page.evaluate((arg) => {"
          " const phone = document.querySelector('input[name=\\'mobile\\']');"
          " const pwd = document.querySelector('input[type=password]');"
          " if (!phone || !pwd) return 'FORM_NOT_FOUND';"
          " const setter = (el, v) => {"
          "   const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;"
          "   s.call(el, v);"
          "   el.dispatchEvent(new Event('input', { bubbles: true }));"
          " };"
          " setter(phone, arg.phone); setter(pwd, arg.pwd);"
          " const cb = document.querySelector('label.privacy-checkbox');"
          " if (cb) cb.click();"
          " return 'OK';"
          "}, { phone: " + _js_str(account) + ", pwd: " + _js_str(password) + " });"
          " return r; }")
    raw = _run_js_file(js, timeout=15)
    return "OK" in (raw or "")


def _submit_login_real_click() -> bool:
    """Click the gradient login button with a REAL (trusted) event.

    playwright-cli click 接受唯一 CSS 选择器；比快照 ref 文本匹配稳健
    （页面上「账号登录」等 Tab 文本都含"登录"，ref 文本匹配易误中）。
    """
    from core.browser.engine import pw
    try:
        pw("click", "div.btn-block__grandient_login",
           timeout=cfg("timeouts.click_action", 10))
        return True
    except Exception as e:
        log(f"登录按钮点击失败：{e}", "WARN")
        return False


def _open_qr_tab_real_click() -> bool:
    """Switch to the QR-code login tab with a REAL click (Element Plus).

    Tab 的 DOM id 是内部编号（实测：账号登录=#tab-1.1 / 学号登录=#tab-2 /
    工号登录=#tab-2.1 / 扫码=#tab-3），不能写死——先按文本找 id 再真实点击。
    """
    from core.browser.engine import pw
    discover_js = ("async (page) => { const r = await page.evaluate(() => {"
                   " const t = [...document.querySelectorAll('.el-tabs__item')]"
                   " .find(el => (el.innerText||'').trim() === '扫码');"
                   " return t ? t.id : ''; }); return r; }")
    tab_id = ""
    try:
        raw = _run_js_file(discover_js, timeout=15)
        import json as _json
        tab_id = (pw_extract_result(raw) or "").strip().strip('"')
    except Exception as e:
        log(f"查找扫码 Tab 失败：{e}", "WARN")
    if tab_id:
        try:
            pw("click", f"#{tab_id}",
               timeout=cfg("timeouts.click_action", 10))
            return True
        except Exception as e:
            log(f"点击扫码 Tab（#{tab_id}）失败：{e}", "WARN")
    log("未找到「扫码」Tab", "ERROR")
    return False


def zhihuishu_login(account_index: int = 0) -> bool:
    """Full login flow: QR first, password+manual-slider fallback.

    Returns True when the session ends up logged in.
    """
    creds = read_all_zhihuishu_credentials()
    if not creds or account_index >= len(creds):
        log(f"Account {account_index} not found in {ACCOUNTS_FILE_NAME}",
            "ERROR")
        return False
    cred = creds[account_index]

    ensure_zhihuishu_browser(account_index)
    pw_goto(LOGIN_URL)
    human_delay(2.0, 0.25)

    # ── 首选：扫码登录（无验证码，实测可行）──
    log("尝试扫码登录（请用「知到」APP 扫描二维码）...")
    try:
        if _open_qr_tab_real_click():
            human_delay(1.5, 0.2)
            _screenshot_ticket(
                f"zhihuishu-qr-login-{account_index}",
                "智慧树扫码登录",
                "请用「知到」APP 扫一扫确认登录；扫码成功后自动继续",
                _QR_LOGIN_TIMEOUT,
            )
            if _wait_login_redirect(_QR_LOGIN_TIMEOUT, "扫码登录"):
                return is_logged_in_on_course_list()
    except Exception as e:
        log(f"扫码登录流程异常：{e}", "WARN")

    # ── 兜底：密码登录 + 易盾滑块人工处理 ──
    log("扫码未完成，回退密码登录（将触发滑块验证，需人工完成）...")
    pw_goto(LOGIN_URL)
    human_delay(2.0, 0.25)
    if not _fill_password_form(cred["account"], cred["password"]):
        log("登录表单填写失败", "ERROR")
        return False
    if not _submit_login_real_click():
        return False
    human_delay(2.5, 0.25)

    # 易盾滑块：截图工单，等待用户在有头窗口手动拖拽
    _screenshot_ticket(
        f"zhihuishu-slider-{account_index}",
        "智慧树滑块验证",
        "请在浏览器窗口中手动拖动滑块完成验证（自动求解为后续专项）",
        _SLIDER_LOGIN_TIMEOUT,
    )
    if _wait_login_redirect(_SLIDER_LOGIN_TIMEOUT, "滑块验证"):
        return is_logged_in_on_course_list()

    log("登录超时（扫码与滑块均未完成）", "ERROR")
    return False


def ensure_logged_in(account_index: int = 0) -> bool:
    """Verify or establish login for an account (profile state first)."""
    ensure_zhihuishu_browser(account_index)
    if is_logged_in_on_course_list():
        log(f"Account {account_index} 已登录（profile 复用）")
        return True
    log(f"Account {account_index} 未登录，开始登录流程...")
    return zhihuishu_login(account_index)
