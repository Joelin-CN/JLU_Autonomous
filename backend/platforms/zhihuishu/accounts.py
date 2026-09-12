"""智慧树凭据子命令：list / add / edit / remove（zhihuishu.txt）。

与超星 accounts 同一单行 JSON 输出协议（ACCOUNTS / ACCOUNTS_OK / ERROR）。
"""

import argparse
import json
import re
import sys

from core.credentials import accounts_file_path, invalidate_cache
from core.logging_setup import log

from platforms.zhihuishu.auth import (
    read_all_zhihuishu_credentials, zhihuishu_accounts_file,
    SESSION_PREFIX, ACCOUNTS_FILE_ENV,
)

DEFAULT_WEBSITE = "https://login.zhihuishu.com/?origin=zhs"


def _write(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def _read_creds() -> list[dict]:
    return read_all_zhihuishu_credentials()


def _render(creds: list[dict]) -> str:
    """Render creds back to the ``{...}`` block format."""
    blocks = []
    for c in creds:
        lines = ["{"]
        if c.get("website") and c["website"] != DEFAULT_WEBSITE:
            lines.append(f"website: {c['website']}")
        lines.append(f"account[{c['index']}]: {c['account']}")
        lines.append(f"password[{c['index']}]: {c['password']}")
        lines.append("}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def _save(creds: list[dict]) -> None:
    path = zhihuishu_accounts_file()
    backup = path.with_suffix(".txt.bak")
    if path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(_render(creds) + "\n", encoding="utf-8")
    invalidate_cache()
    # 写后读校验
    if not _read_creds():
        raise RuntimeError("read-back verification failed after save")


def _cmd_add(args) -> None:
    creds = _read_creds()
    next_idx = (max(c["index"] for c in creds) + 1) if creds else 0
    creds.append({"account": args.account, "password": args.password,
                  "website": args.website or DEFAULT_WEBSITE,
                  "index": next_idx})
    _save(creds)
    _write({"type": "ACCOUNTS_OK", "action": "add", "index": next_idx})


def _cmd_edit(args) -> None:
    creds = _read_creds()
    for c in creds:
        if c["index"] == args.index:
            if args.account:
                c["account"] = args.account
            if args.password:
                c["password"] = args.password
            if args.website:
                c["website"] = args.website
            _save(creds)
            _write({"type": "ACCOUNTS_OK", "action": "edit", "index": args.index})
            return
    _write({"type": "ERROR", "error": f"Account index {args.index} not found"})


def _cmd_remove(args) -> None:
    creds = _read_creds()
    remaining = [c for c in creds if c["index"] != args.index]
    if len(remaining) == len(creds):
        _write({"type": "ERROR", "error": f"Account index {args.index} not found"})
        return
    _save(remaining)
    _write({"type": "ACCOUNTS_OK", "action": "remove", "index": args.index})


def main() -> None:
    parser = argparse.ArgumentParser(description="Zhihuishu accounts CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")

    p_add = sub.add_parser("add")
    p_add.add_argument("--account", required=True)
    p_add.add_argument("--password", required=True)
    p_add.add_argument("--website", default=None)

    p_edit = sub.add_parser("edit")
    p_edit.add_argument("--index", type=int, required=True)
    p_edit.add_argument("--account", default=None)
    p_edit.add_argument("--password", default=None)
    p_edit.add_argument("--website", default=None)

    p_rm = sub.add_parser("remove")
    p_rm.add_argument("--index", type=int, required=True)

    args = parser.parse_args()
    try:
        if args.command == "list":
            creds = _read_creds()
            _write({"type": "ACCOUNTS", "accounts": [
                {"index": c["index"], "account": c["account"],
                 "website": c["website"]} for c in creds]})
        elif args.command == "add":
            _cmd_add(args)
        elif args.command == "edit":
            _cmd_edit(args)
        elif args.command == "remove":
            _cmd_remove(args)
    except Exception as e:
        log(f"accounts 命令失败：{e}", "ERROR")
        _write({"type": "ERROR", "error": str(e)})


if __name__ == "__main__":
    main()
