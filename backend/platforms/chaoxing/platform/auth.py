"""
Chaoxing authentication — credential reading, browser session management, login.

Handles multi-account credential parsing from passwords/chaoxing.txt,
browser session lifecycle (open, check, ensure), and two login methods:
    1. JS DOM-based login (primary — reliable, no snapshot-ref fragility)
    2. Snapshot-based login (fallback — uses clipboard paste via PowerShell)
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path

import threading

from core.constants import WORKSPACE, TMP_DIR, CREDS_DIR, CHROME_PROFILES_DIR
from core.config import cfg
from core.session import _get_active_session
from core.logging_setup import log
from core.browser.engine import (
    pw, pw_snapshot, pw_click, pw_goto,
    PlaywrightCliMissingError, ensure_cli_available,
)
from core.browser.js_runner import pw_run_code_file, pw_extract_result
from core.utils import human_delay

# playwright-cli's `list` talks to a single daemon socket. When multiple
# account threads probe at once (3-account start), the daemon can queue the
# calls and leave every caller blocked. Serialize the probes and bound them so
# a wedged daemon degrades to "unknown" instead of hanging a whole lane.
_PLAYWRIGHT_LIST_LOCK = threading.Lock()


# ── Credential Parsing ───────────────────────────────────────────

def _parse_credential_block(block: str) -> dict | None:
    """Parse a single credential block from chaoxing.txt.

    Handles both formats:
        account:13200003918
        account[0]:13200003918
        website[0]:https://example.com/login

    Returns {account, password, website, index} or None.
    """
    website = ""
    account = ""
    password = ""
    index = 0

    for line in block.split("\n"):
        line = line.strip()
        if line in ("{", "}", ""):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'").strip('{}').strip()

        # Extract index from account[N] / password[N] / website[N]
        m = re.match(r'(account|password|website|网站)\[(\d+)\]', key)
        if m:
            key = m.group(1)
            index = int(m.group(2))

        if key in ("website", "网站"):
            website = value
        elif key in ("account", "账号"):
            account = value
        elif key in ("password", "密码"):
            password = value

    if account and password:
        if not website:
            website = (
                "https://passport2.chaoxing.com/login"
                "?fid=&newversion=true"
                "&refer=https%3A%2F%2Fi.chaoxing.com"
            )
        return {"account": account, "password": password, "website": website, "index": index}

    return None


# ── Credential Cache ─────────────────────────────────────────────
_ALL_CREDS_CACHE = None
_ALL_CREDS_LOCK = threading.Lock()


def accounts_file_path() -> Path:
    """Resolve the active Chaoxing account file (env override wins)."""
    override = os.environ.get("CHAOXING_ACCOUNTS_FILE")
    return Path(override) if override else CREDS_DIR / "chaoxing.txt"


def invalidate_credentials_cache() -> None:
    """Drop the cached credential parse so the next read hits disk."""
    global _ALL_CREDS_CACHE
    with _ALL_CREDS_LOCK:
        _ALL_CREDS_CACHE = None


def read_all_chaoxing_credentials() -> list[dict]:
    """Read ALL Chaoxing accounts from passwords/chaoxing.txt.

    The file can contain multiple account blocks separated by blank lines
    or braces. Each block may use account[N] / password[N] syntax to
    explicitly number accounts.

    Returns list of dicts: [{account, password, website, index}, ...]

    Result is cached after first parse. Thread-safe via lock.
    """
    global _ALL_CREDS_CACHE
    with _ALL_CREDS_LOCK:
        if _ALL_CREDS_CACHE is not None:
            return list(_ALL_CREDS_CACHE)

        cred_file = accounts_file_path()
        if not cred_file.exists():
            log(f"Credential file not found: {cred_file}", "ERROR")
            _ALL_CREDS_CACHE = []
            return []

        content = cred_file.read_text(encoding="utf-8")

        # Split into blocks: split on }\n{ or }\n\n{ boundaries
        blocks = re.split(r'\}\s*\{', content)
        for i in range(len(blocks)):
            blocks[i] = blocks[i].strip()
            if not blocks[i].startswith("{"):
                blocks[i] = "{\n" + blocks[i]
            blocks[i] = blocks[i].rstrip('}').rstrip() + "\n}"

        accounts = []
        seen_accounts = set()
        used_indices = set()
        for block in blocks:
            cred = _parse_credential_block(block)
            if cred and cred["account"] not in seen_accounts:
                if cred["index"] == 0 and used_indices:
                    cred["index"] = max(used_indices) + 1
                seen_accounts.add(cred["account"])
                used_indices.add(cred["index"])
                accounts.append(cred)
                log(f"Loaded credentials [{cred['index']}]: {cred['account'][:3]}***"
                    f" (website={'default' if 'fid' in cred['website'] else 'custom'})")

        if not accounts:
            log("Could not parse any credentials from chaoxing.txt", "ERROR")
        else:
            log(f"Total accounts loaded: {len(accounts)}")

        _ALL_CREDS_CACHE = accounts
        return list(accounts)


def read_chaoxing_credentials() -> tuple[str, str, str] | None:
    """Read the FIRST Chaoxing account from passwords/chaoxing.txt.

    Backward-compatible wrapper. Returns (account, password, login_url) or None.
    For multi-account support, use read_all_chaoxing_credentials().
    """
    all_creds = read_all_chaoxing_credentials()
    if not all_creds:
        return None
    cred = all_creds[0]
    return (cred["account"], cred["password"], cred["website"])


# ── Browser Session Management ───────────────────────────────────

def is_chaoxing_browser_open() -> bool:
    """Check if the chaoxing browser session is already running."""
    session = _get_active_session()
    cli = cfg("playwright_cli", "playwright-cli.cmd")
    ensure_cli_available(cli)
    with _PLAYWRIGHT_LIST_LOCK:
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


def _session_is_headed(session: str) -> bool | None:
    """Return whether the named playwright-cli session is running headed.

    Parses `playwright-cli list`, which prints one block per session::

        - chaoxing-chrome-0:
          - status: open
          - browser-type: chrome
          - headed: false

    Returns True/False for the matching session's `headed:` field, or None if
    the session isn't listed or the field can't be found. Used to detect a
    stale session whose headed-ness no longer matches the desired mode — see
    ensure_chaoxing_browser.
    """
    cli = cfg("playwright_cli", "playwright-cli.cmd")
    with _PLAYWRIGHT_LIST_LOCK:
        try:
            result = subprocess.run(
                [cli, "list"],
                cwd=str(WORKSPACE), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=8, shell=False,
            )
        except Exception:
            return None

    in_block = False
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        # Session header lines look like "- chaoxing-chrome-0:"
        if line.startswith("-") and line.rstrip(":").endswith(session):
            in_block = True
            continue
        if in_block:
            # A new session header ends the current block.
            if line.startswith("-") and line.endswith(":") and "headed" not in line:
                in_block = False
                continue
            if line.lower().startswith("- headed:") or line.lower().startswith("headed:"):
                return "true" in line.lower()
    return None


def ensure_chaoxing_browser(account_index: int = 0) -> bool:
    """Ensure the chaoxing browser session is open IN THE RIGHT MODE.

    Opens it if not running. If a session is already open but its headed-ness
    no longer matches the desired CHAOXING_HEADED (e.g. the user toggled
    "无头模式" between runs, or a stale headless session lingered), it is
    closed and reopened so the toggle actually takes effect. Login is NOT lost
    on the close/reopen — cookies live in the on-disk --user-data-dir profile.

    Chrome is launched with --disable-gpu to eliminate VRAM bottleneck,
    and profiles are stored on E: drive to avoid C: drive pressure.

    Returns True if ready.
    """
    session = _get_active_session()
    _headed = os.environ.get("CHAOXING_HEADED", "0") == "1"

    if is_chaoxing_browser_open():
        current_headed = _session_is_headed(session)
        # Only act when we can positively confirm a mismatch; None (unknown)
        # means "leave the working session alone".
        if current_headed is not None and current_headed != _headed:
            log(f"Session {session} is "
                f"{'headed' if current_headed else 'headless'} but "
                f"{'headed' if _headed else 'headless'} requested — "
                f"reopening...")
            close_chaoxing_browser(account_index)
            time.sleep(1)
            # fall through to the open path below
        else:
            return True

    # A previous run may have left orphaned chrome.exe processes (e.g. the
    # Python process was force-killed before its finally block ran). Sweep
    # them before opening so the new session does not contend for the profile.
    _kill_orphaned_chrome(account_index)

    cli = cfg("playwright_cli", "playwright-cli.cmd")
    ensure_cli_available(cli)
    log(f"Opening Chaoxing browser session ({session})...")

    all_creds = read_all_chaoxing_credentials()
    if all_creds and account_index < len(all_creds):
        login_url = all_creds[account_index]["website"]
    else:
        login_url = (
            "https://passport2.chaoxing.com/login"
            "?fid=&newversion=true"
            "&refer=https%3A%2F%2Fi.chaoxing.com"
        )

    # Keep the Chrome profile under the writable data root so a packaged
    # (read-only) install still writes to a per-user location. CHAOXING_DATA_DIR
    # controls the root; in dev it is the repo-level data/ directory, when
    # packaged it is userData/data.
    #
    # NOTE: playwright-cli's `open` only accepts --browser/--config/--headed/
    # --persistent/--profile. It has NO --user-data-dir, --disk-cache-dir, or
    # raw Chrome-arg passthrough. Passing those made the whole `open` command
    # fail (RC=1, "Unknown options"), so the browser was silently auto-spawned
    # by the daemon in its default (headless, C:-drive) mode — which is why the
    # 无头 toggle and the E:-drive profile both appeared to do nothing. The
    # persistent profile dir is passed via --profile; --disable-gpu / cache-dir
    # are not expressible here and are dropped.
    profile_dir = str(CHROME_PROFILES_DIR / f"account-{account_index}")

    cmd = [
        cli, f"-s={session}", "open", "--browser=chrome", "--persistent",
        f"--profile={profile_dir}",
    ]
    if _headed:
        cmd.append("--headed")
    cmd.append("about:blank")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(WORKSPACE), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30, shell=False,
        )
    except FileNotFoundError:
        raise PlaywrightCliMissingError(cli)
    if result.returncode != 0:
        # Surface the failure instead of letting the daemon silently auto-spawn
        # a default (headless) session — the bug that masked the 无头 toggle.
        log(f"[!] playwright-cli open failed (rc={result.returncode}): "
            f"{(result.stderr or result.stdout or '').strip()[:300]}")
    human_delay(4.0, 0.25)

    # Navigate via the engine after the session is up: pw_goto JSON-escapes
    # the URL, so query strings containing '&' survive the cmd.exe wrapper.
    try:
        pw_goto(login_url)
    except Exception as e:
        log(f"Navigate to login failed after open: {e}", "WARN")

    # Set window title (cosmetic, only visible in headed mode)
    try:
        title_js = f"async (page) => {{ await page.evaluate(() => {{ document.title = '超星 Account {account_index}'; }}); return 'ok'; }}"
        # Deferred import to avoid circular dependency
        from ..browser.js_runner import _run_js_file
        _run_js_file(title_js, timeout=5)
    except Exception:
        pass

    return is_chaoxing_browser_open()


def close_chaoxing_browser(account_index: int = 0) -> bool:
    """Close the persistent browser session for an account.

    playwright-cli keeps Chrome alive as a daemon session between commands;
    nothing tears it down when a job ends, so without this the Chrome
    processes linger after every run (visible in Task Manager). Login state
    is NOT lost: cookies live in the on-disk --user-data-dir profile, so the
    next ensure_chaoxing_browser() reopens already logged in.

    Targets chaoxing-chrome-{account_index} explicitly rather than the
    thread-local active session, so it is safe to call from a finally block
    after set_active_session may have been cleared.

    Returns True if the close command ran without error (idempotent: closing
    an already-closed session is fine).
    """
    session = f"chaoxing-chrome-{account_index}"
    cli = cfg("playwright_cli", "playwright-cli.cmd")
    try:
        result = subprocess.run(
            [cli, f"-s={session}", "close"],
            cwd=str(WORKSPACE), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20, shell=True,
        )
        if result.returncode != 0 and result.stderr:
            log(f"[Account {account_index}] close warning: "
                f"{result.stderr[:150]}", "WARN")
        else:
            log(f"[Account {account_index}] browser session closed")
        ok = result.returncode == 0
    except FileNotFoundError:
        log(f"[Account {account_index}] {PlaywrightCliMissingError(cli)}",
            "WARN")
        ok = False
    except Exception as e:
        log(f"[Account {account_index}] failed to close browser: {e}", "WARN")
        ok = False

    # Give the daemon a moment to reap the Chrome tree, then sweep anything
    # that still references this account profile (belt-and-suspenders: the
    # daemon can be wedged or the close can race a force-kill).
    human_delay(1.0, 0.2)
    _kill_orphaned_chrome(account_index)
    return ok


def _kill_orphaned_chrome(account_index: int) -> int:
    """Force-terminate chrome.exe processes bound to an account profile.

    Thin platform wrapper over the generic core.browser.orphans sweep
    (keeps the historical call sites/signature). Chaoxing profiles use the
    legacy flat layout: CHROME_PROFILES_DIR/account-N.

    Returns the number of processes terminated (0 when nothing matched).
    """
    from core.browser.orphans import kill_orphaned_chrome
    return kill_orphaned_chrome(CHROME_PROFILES_DIR / f"account-{account_index}")


# ── Login Methods ────────────────────────────────────────────────

def chaoxing_login(account_index: int = 0) -> bool:
    """Automate Chaoxing login using stored credentials.

    Opens the login page (and browser if needed), fills account/password
    directly via JS DOM manipulation, clicks login, and verifies the
    landing page.

    Args:
        account_index: which account from passwords/chaoxing.txt (0-based).

    Returns True if login succeeded (or already logged in).
    """
    # 0. Ensure browser is open
    if not ensure_chaoxing_browser(account_index):
        log("Failed to open Chaoxing browser", "ERROR")
        return False

    # 1. Quick check: already logged in?
    snap = pw_snapshot()
    if "个人空间" in snap or "i.chaoxing.com/base" in snap:
        log(f"Already logged into Chaoxing (account {account_index})", "OK")
        return True

    # 1b. Stale-session recovery: a session that is listed but stuck on a
    # blank/crashed page would make every pw_goto time out. Close and reopen
    # once before going down the normal login path.
    if "about:blank" in snap or "页面崩溃" in snap or "aw, snap" in snap.lower():
        log("Session is on a blank/crashed page, re-creating browser...", "WARN")
        close_chaoxing_browser(account_index)
        if not ensure_chaoxing_browser(account_index):
            log("Failed to reopen Chaoxing browser", "ERROR")
            return False
        snap = pw_snapshot()
        if "个人空间" in snap or "i.chaoxing.com/base" in snap:
            log(f"Already logged into Chaoxing (account {account_index})", "OK")
            return True

    # 2. Read credentials for this account
    all_creds = read_all_chaoxing_credentials()
    if not all_creds or account_index >= len(all_creds):
        log(f"Cannot login: no credentials for account index {account_index}", "ERROR")
        return False

    cred = all_creds[account_index]
    account = cred["account"]
    password = cred["password"]
    login_url = cred["website"]

    # 3. Navigate to login page (only if not already there)
    already_on_login = "用户登录" in snap and "passport2.chaoxing.com" in snap
    if not already_on_login:
        log("Navigating to Chaoxing login page...")
        pw_goto(login_url)
        human_delay(3.0, 0.25)

        snap = pw_snapshot()

        if "个人空间" in snap:
            log("Already logged in (redirected from login page)", "OK")
            return True

        if "用户登录" not in snap and "passport2.chaoxing.com" not in snap:
            log("Unexpected page, retrying with base login URL...", "WARN")
            pw_goto("https://passport2.chaoxing.com/login")
            human_delay(3.0, 0.25)
            snap = pw_snapshot()
            if "个人空间" in snap:
                log("Already logged in (redirected)", "OK")
                return True
    else:
        log("Already on login page, skipping navigation to avoid CAPTCHA")

    # 4. Fill form + click login via JS
    log("Filling login form via JS DOM manipulation...")

    safe_account = json.dumps(account)
    safe_password = json.dumps(password)

    login_js = f"""
    async (page) => {{
        let acctInput = null;
        const inputs = await page.locator('input').all();
        for (const inp of inputs) {{
            const ph = (await inp.getAttribute('placeholder') || '').toLowerCase();
            const tp = (await inp.getAttribute('type') || '').toLowerCase();
            if (ph.includes('手机') || ph.includes('超星') || ph.includes('账号') ||
                (tp === 'text' && !acctInput && ph === '')) {{
                acctInput = inp;
                break;
            }}
        }}

        let pwdInput = null;
        for (const inp of inputs) {{
            const ph = (await inp.getAttribute('placeholder') || '').toLowerCase();
            const tp = (await inp.getAttribute('type') || '').toLowerCase();
            if (tp === 'password' || ph.includes('密码')) {{
                pwdInput = inp;
                break;
            }}
        }}

        if (!acctInput || !pwdInput) {{
            return JSON.stringify({{
                ok: false, reason: 'inputs-not-found',
                acctFound: !!acctInput, pwdFound: !!pwdInput,
            }});
        }}

        await acctInput.click();
        await page.waitForTimeout(200);
        await acctInput.fill({safe_account});
        await page.waitForTimeout(300);

        await pwdInput.click();
        await page.waitForTimeout(200);
        await pwdInput.fill({safe_password});
        await page.waitForTimeout(300);

        const buttons = await page.locator('button').all();
        let loginBtn = null;
        for (const btn of buttons) {{
            const text = (await btn.textContent() || '').trim();
            if (text === '登录' || text.includes('登') || text.includes('录')) {{
                loginBtn = btn; break;
            }}
        }}
        if (!loginBtn) {{
            for (const btn of buttons) {{
                const tp = await btn.getAttribute('type');
                if (tp === 'submit') {{ loginBtn = btn; break; }}
            }}
        }}
        if (!loginBtn) {{
            return JSON.stringify({{ok: false, reason: 'login-button-not-found'}});
        }}

        await loginBtn.click();
        // Human-like: brief pause, then wait for the redirect off the login
        // page instead of a blind fixed sleep.
        await page.waitForTimeout(1200 + Math.floor(Math.random() * 800));
        await page.waitForURL(
            (u) => !u.includes('passport2.chaoxing.com/login'),
            {{ timeout: 10000 }}
        ).catch(() => {{}});
        await page.waitForTimeout(800 + Math.floor(Math.random() * 1200));

        const url = page.url();
        const title = await page.title();
        const stillOnLogin = (
            url.includes('passport2.chaoxing.com/login') ||
            title.includes('用户登录')
        );
        const isLoggedIn = !stillOnLogin && (
            url.startsWith('https://i.chaoxing.com') ||
            url.includes('chaoxing.com/space') ||
            title.includes('个人空间') ||
            // University-branded space pages (e.g. i.mooc.chaoxing.com)
            (url.includes('mooc.chaoxing.com') && url.includes('/space'))
        );

        const bodyText = await page.locator('body').innerText();
        const hasCaptcha = (
            bodyText.includes('操作异常') ||
            bodyText.includes('滑块验证') ||
            bodyText.includes('请输入验证码') ||
            bodyText.includes('验证码已发送')
        );

        return JSON.stringify({{
            ok: isLoggedIn,
            reason: isLoggedIn ? 'logged-in' :
                    hasCaptcha ? 'captcha' :
                    stillOnLogin ? 'still-on-login' : 'unknown',
            url: url.substring(0, 120), title: title,
        }});
    }}
    """

    import tempfile as _tmp
    import os as _os

    js_file = _tmp.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(TMP_DIR), encoding='utf-8')
    js_file.write(login_js)
    js_file.close()

    try:
        raw = pw_run_code_file(js_file.name, timeout=30)
        result_str = pw_extract_result(raw)
        result = json.loads(result_str)
    except Exception as e:
        log(f"Login JS execution failed: {e}", "ERROR")
        result = {"ok": False, "reason": f"js-error:{e}"}
    finally:
        try:
            _os.unlink(js_file.name)
        except:
            pass

    log(f"Login JS result: {json.dumps(result, ensure_ascii=False)}")

    if result.get("ok"):
        log("Chaoxing login SUCCESS!", "OK")
        return True

    reason = result.get("reason", "?")
    if reason == "captcha":
        log("CAPTCHA or verification detected — manual intervention needed", "ERROR")
    elif reason == "still-on-login":
        log("Still on login page — check credentials in passwords/chaoxing.txt", "ERROR")
    elif reason == "inputs-not-found":
        log("JS couldn't find form inputs — trying snapshot-based fallback...")
        return _chaoxing_login_via_snapshot(account, password)
    else:
        log(f"Login failed: {reason}", "ERROR")

    return False


def _chaoxing_login_via_snapshot(account: str, password: str) -> bool:
    """Fallback login: use snapshot refs + clipboard paste.

    Only called when the primary JS-based login can't find form elements.
    """
    session = _get_active_session()
    cli = cfg("playwright_cli", "playwright-cli.cmd")

    snap = pw_snapshot()
    log("Attempting snapshot-based login (fallback)...")

    all_textbox_refs = re.findall(r"textbox[^\n]*?\[ref=(e\d+)\]", snap)
    log(f"  Snapshot textbox refs: {all_textbox_refs}")

    if len(all_textbox_refs) >= 2:
        account_ref = all_textbox_refs[0]
        password_ref = all_textbox_refs[1]
        log(f"  Positional refs: acct={account_ref}, pwd={password_ref}")
    else:
        account_ref = _find_login_field_ref(snap, ["手机号", "超星号", "账号"])
        password_ref = _find_login_field_ref(snap, ["密码", "学习通密码"])
        if account_ref == password_ref and len(all_textbox_refs) >= 2:
            password_ref = all_textbox_refs[1]
        elif account_ref == password_ref:
            log("  ERROR: Only one textbox ref found, cannot fill both fields", "ERROR")
            return False

    login_ref = _find_login_button_ref(snap)

    if not account_ref or not password_ref or not login_ref:
        log(f"  Missing refs: acct={account_ref}, pwd={password_ref}, login={login_ref}", "ERROR")
        return False

    if account_ref == password_ref:
        log(f"  FATAL: Same ref {account_ref} for account AND password — aborting", "ERROR")
        return False

    log(f"  Filling: acct={account_ref}, pwd={password_ref}, login={login_ref}")

    # Use JS DOM injection to fill fields — avoids clipboard credential leak.
    # The password is JSON-escaped and written to a temp JS file (cleaned up after).
    safe_account = json.dumps(account)
    safe_password = json.dumps(password)

    fill_js = f"""
    async (page) => {{
        const inputs = await page.locator('input').all();
        let acctInp = null, pwdInp = null;
        for (const inp of inputs) {{
            const tp = (await inp.getAttribute('type') || '').toLowerCase();
            const ph = (await inp.getAttribute('placeholder') || '').toLowerCase();
            if (tp === 'password' || ph.includes('密码')) {{
                pwdInp = inp;
            }} else if (!acctInp && (tp === 'text' || tp === 'tel' || ph.includes('手机') || ph.includes('账号'))) {{
                acctInp = inp;
            }}
        }}
        if (!acctInp || !pwdInp) {{
            return JSON.stringify({{ok: false, reason: 'inputs-not-found',
                acctFound: !!acctInp, pwdFound: !!pwdInp}});
        }}
        await acctInp.click();
        await page.waitForTimeout(200);
        await acctInp.fill({safe_account});
        await page.waitForTimeout(300);
        await pwdInp.click();
        await page.waitForTimeout(200);
        await pwdInp.fill({safe_password});
        await page.waitForTimeout(300);
        return JSON.stringify({{ok: true, reason: 'filled'}});
    }}
    """

    import tempfile as _tmp
    import os as _os

    js_file = _tmp.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(TMP_DIR), encoding='utf-8')
    js_file.write(fill_js)
    js_file.close()

    try:
        raw = pw_run_code_file(js_file.name, timeout=20)
        fill_result = json.loads(pw_extract_result(raw))
        if not fill_result.get("ok"):
            log(f"JS fill failed in snapshot fallback: {fill_result.get('reason')}", "WARN")
    except Exception as e:
        log(f"JS fill exception in snapshot fallback: {e}", "WARN")
    finally:
        try:
            _os.unlink(js_file.name)
        except Exception:
            pass

    # Clear clipboard to prevent credential lingering (belt-and-suspenders)
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             '$null = Set-Clipboard ""'],
            cwd=str(WORKSPACE), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=5, shell=False,
        )
    except Exception:
        pass

    human_delay(0.5, 0.4)

    # Click login
    pw_click(login_ref)
    human_delay(5.0, 0.2)

    snap = pw_snapshot()
    if "个人空间" in snap or "i.chaoxing.com/base" in snap:
        log("Chaoxing login SUCCESS (via fallback)!", "OK")
        return True

    if "验证" in snap or "captcha" in snap.lower() or "滑块" in snap:
        log("CAPTCHA after fallback login", "ERROR")
    elif "用户登录" in snap:
        log("Still on login page after fallback — bad credentials?", "ERROR")
    else:
        log(f"Fallback result unclear: {snap[:200]}", "WARN")
    return False


def _find_login_field_ref(snap: str, labels: list[str]) -> str | None:
    """Find a form field ref by its label/placeholder text in snapshot."""
    lines = snap.split("\n")
    for i, line in enumerate(lines):
        for label in labels:
            if label in line:
                for j in range(max(0, i - 5), min(len(lines), i + 5)):
                    m = re.search(r"textbox[^\n]*?\[ref=(e\d+)\]", lines[j])
                    if m:
                        return m.group(1)
    textbox_refs = re.findall(r"textbox[^\n]*?\[ref=(e\d+)\]", snap)
    if textbox_refs:
        if len(textbox_refs) >= 2 and any("密码" in l for l in labels):
            return textbox_refs[1]
        return textbox_refs[0]
    return None


def _find_login_button_ref(snap: str) -> str | None:
    """Find the login button ref on the Chaoxing login page snapshot."""
    for pattern in [
        r'button\s+"登录"\s+\[ref=(e\d+)\]',
        r'button\s+"登\s*录"\s+\[ref=(e\d+)\]',
    ]:
        m = re.search(pattern, snap)
        if m:
            return m.group(1)

    lines = snap.split("\n")
    for i, line in enumerate(lines):
        if "登录" in line and "button" in line:
            m = re.search(r"\[ref=(e\d+)\]", line)
            if m:
                return m.group(1)
    for i, line in enumerate(lines):
        if "登录" == line.strip().strip('"').strip("'") or line.strip() == '"登录"':
            for j in range(max(0, i - 3), min(len(lines), i + 3)):
                m = re.search(r"\[ref=(e\d+)\]", lines[j])
                if m:
                    return m.group(1)
    return None
