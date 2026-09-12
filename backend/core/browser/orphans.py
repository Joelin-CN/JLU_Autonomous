"""按 profile 目录清扫孤儿 Chrome 进程（平台无关）。

playwright-cli 的 daemon 正常会在 close 时回收 Chrome 子进程；但当 daemon
卡死或 Python 进程在 finally 块之前被强杀时，整棵 Chrome 进程树可能滞留在
任务管理器中。本模块按 profile 目录精确匹配 chrome.exe 命令行后强杀，
绝不触碰用户自己的浏览器。

各平台调用方式：
    from core.browser.orphans import kill_orphaned_chrome
    kill_orphaned_chrome(profile_dir)   # 传入该账号的 profile 绝对路径
"""

import subprocess

from core.constants import CHROME_PROFILES_DIR
from core.logging_setup import log


def kill_orphaned_chrome(profile_dir) -> int:
    """Force-terminate chrome.exe processes bound to a profile directory.

    Args:
        profile_dir: 该账号的 Chrome profile 目录（Path 或 str）。

    Returns:
        被终止的进程数（无匹配时为 0）。
    """
    escaped = str(profile_dir).replace("'", "''")
    script = (
        "$ps = Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\";"
        f"$hits = $ps | Where-Object {{ $_.CommandLine -like '*{escaped}*' }};"
        "$ids = @($hits | ForEach-Object { $_.ProcessId });"
        "foreach ($id in $ids) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue };"
        "[Console]::Out.Write($ids.Count)"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=20, shell=False,
        )
        stdout = getattr(result, "stdout", None) or ""
        count = int(stdout.strip() or "0")
        if count:
            log(f"Killed {count} orphaned Chrome process(es) for "
                f"{str(profile_dir)[-40:]}", "WARN")
        return count
    except Exception as e:
        log(f"Orphaned Chrome cleanup failed: {e}", "WARN")
        return 0


def profile_dir_for_session(session: str, account_index: int):
    """Resolve the persistent profile dir for a session name.

    会话命名约定为 ``{platform}-chrome-{N}``。历史遗留：超星 profile 直接
    平铺在 CHROME_PROFILES_DIR/account-N（迁移目录会丢失既有登录态，故保持）；
    新平台（zhihuishu 等）按平台子目录隔离：CHROME_PROFILES_DIR/<platform>/account-N。
    """
    tag = session.split("-chrome")[0] if "-chrome" in session else "chaoxing"
    if tag == "chaoxing":
        return CHROME_PROFILES_DIR / f"account-{account_index}"
    return CHROME_PROFILES_DIR / tag / f"account-{account_index}"
