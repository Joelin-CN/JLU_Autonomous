"""通用凭据文件解析（``{...}`` 块格式），供各平台复用。

文件格式（与超星 chaoxing.txt 兼容，多块以 ``}`` + 空白 + ``{`` 分隔）::

    {
    website: https://login.example.com
    account[0]: 13200003918
    password[0]: example
    }
    {
    account[1]: 13200003919
    password[1]: example
    }

键支持中文别名（账号/密码/网站）；未编号块自动递增序号。
结果按文件路径缓存，线程安全。
"""

import os
import re
import threading
from pathlib import Path

from core.constants import CREDS_DIR
from core.logging_setup import log

_LOCK = threading.Lock()
_CACHE: dict[str, list[dict]] = {}


def parse_credential_block(block: str, default_website: str = "") -> dict | None:
    """Parse a single ``{...}`` block; return {account, password, website, index} or None."""
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

        m = re.match(r'(account|password|website|网站|账号|密码)\[(\d+)\]', key)
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
        return {
            "account": account,
            "password": password,
            "website": website or default_website,
            "index": index,
        }
    return None


def read_accounts_file(path: Path, *, default_website: str = "",
                       label: str = "") -> list[dict]:
    """Read and parse one credentials file (cached by path, thread-safe).

    Args:
        path: 凭据文件绝对路径。
        default_website: 块内未提供 website 时的默认登录页。
        label: 日志中展示的文件标签（如 "zhihuishu.txt"）。
    """
    key = str(path)
    with _LOCK:
        if key in _CACHE:
            return list(_CACHE[key])

        if not path.exists():
            log(f"Credential file not found: {path}", "ERROR")
            _CACHE[key] = []
            return []

        content = path.read_text(encoding="utf-8")
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
            cred = parse_credential_block(block, default_website)
            if cred and cred["account"] not in seen_accounts:
                if cred["index"] == 0 and used_indices:
                    cred["index"] = max(used_indices) + 1
                seen_accounts.add(cred["account"])
                used_indices.add(cred["index"])
                accounts.append(cred)
                log(f"Loaded credentials [{cred['index']}]: "
                    f"{cred['account'][:3]}***")

        if not accounts:
            log(f"Could not parse any credentials from {label or path.name}",
                "ERROR")
        else:
            log(f"Total accounts loaded: {len(accounts)}")

        _CACHE[key] = accounts
        return list(accounts)


def invalidate_cache() -> None:
    """Drop all cached parses so subsequent reads hit disk."""
    with _LOCK:
        _CACHE.clear()


def accounts_file_path(env_var: str, file_name: str) -> Path:
    """Resolve a platform credentials file (env override wins)."""
    override = os.environ.get(env_var)
    return Path(override) if override else CREDS_DIR / file_name
