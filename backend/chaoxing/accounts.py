"""
CLI entry point for listing and managing Chaoxing accounts.

Usage::

    python -m chaoxing.accounts list
    python -m chaoxing.accounts add --account 138... --password ... [--website ...]
    python -m chaoxing.accounts edit --index 0 [--password ...] [--website ...]
    python -m chaoxing.accounts remove --index 0

Emits exactly ONE line of JSON to stdout:

    list success: {"type":"ACCOUNTS","accounts":[{"index":0,"account":"13800000000"}, ...]}
    mutation ok:  {"type":"ACCOUNTS_OK","action":"add|edit|remove","index":N,
                    "account":"..."}
    failure:      {"type":"ERROR","error":"<msg>","detail":"<type>"}  + exit 1

Passwords are NEVER emitted. The active file honours CHAOXING_ACCOUNTS_FILE
(falling back to data/passwords/chaoxing.txt) via accounts_file_path().
"""

import argparse
import json
import os
import re
import sys

from .platform import auth
from .platform.auth import (
    accounts_file_path,
    _parse_credential_block,
    invalidate_credentials_cache,
)
from .logging_setup import log


def _write_json_line(obj: dict) -> None:
    """Write a single compact JSON object as one line to stdout, then flush."""
    line = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _atomic_write_text(path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _backup_existing(path) -> None:
    if path.exists():
        path.with_name(path.name + ".bak").write_bytes(path.read_bytes())


def _read_creds() -> list[dict]:
    path = accounts_file_path()
    if not path.exists():
        return []
    blocks = re.split(r"\}\s*\{", path.read_text(encoding="utf-8"))
    for i in range(len(blocks)):
        blocks[i] = blocks[i].strip()
        if not blocks[i].startswith("{"):
            blocks[i] = "{\n" + blocks[i]
        blocks[i] = blocks[i].rstrip("}").rstrip() + "\n}"
    creds = []
    for block in blocks:
        cred = _parse_credential_block(block)
        if cred:
            creds.append(cred)
    return creds


def _render(creds: list[dict]) -> str:
    parts = []
    for c in creds:
        idx = c.get("index", 0)
        parts.append("{\n")
        parts.append(f"account[{idx}]: {c['account']}\n")
        parts.append(f"password[{idx}]: {c['password']}\n")
        if c.get("website"):
            parts.append(f"website[{idx}]: {c['website']}\n")
        parts.append("}\n")
    return "\n".join(parts)


def _save(creds: list[dict]) -> None:
    path = accounts_file_path()
    _backup_existing(path)
    _atomic_write_text(path, _render(creds))
    invalidate_credentials_cache()
    if len(_read_creds()) != len(creds):
        raise RuntimeError("write-back verification failed")


def _cmd_add(args) -> None:
    creds = _read_creds()
    if any(c["account"] == args.account for c in creds):
        raise ValueError(f"duplicate account: {args.account[:3]}***")
    used = {int(c.get("index", 0)) for c in creds}
    idx = 0
    while idx in used:
        idx += 1
    creds.append({"account": args.account, "password": args.password,
                  "website": args.website or "", "index": idx})
    _save(creds)
    log(f"Account add: index={idx} account={args.account[:3]}***", "OK")
    _write_json_line({"type": "ACCOUNTS_OK", "action": "add",
                      "index": idx, "account": args.account})


def _cmd_edit(args) -> None:
    creds = _read_creds()
    for c in creds:
        if int(c.get("index", -1)) == args.index:
            if args.password:
                c["password"] = args.password
            if args.website is not None:
                c["website"] = args.website
            _save(creds)
            log(f"Account edit: index={args.index} account={c['account'][:3]}***",
                "OK")
            _write_json_line({"type": "ACCOUNTS_OK", "action": "edit",
                              "index": args.index, "account": c["account"]})
            return
    raise ValueError(f"index not found: {args.index}")


def _cmd_remove(args) -> None:
    before = _read_creds()
    creds = [c for c in before if int(c.get("index", -1)) != args.index]
    if len(creds) == len(before):
        raise ValueError(f"index not found: {args.index}")
    _save(creds)
    log(f"Account remove: index={args.index}", "OK")
    _write_json_line({"type": "ACCOUNTS_OK", "action": "remove",
                      "index": args.index, "account": None})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chaoxing.accounts")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list")
    p_add = sub.add_parser("add")
    p_add.add_argument("--account", required=True)
    p_add.add_argument("--password", required=True)
    p_add.add_argument("--website", default=None)
    p_edit = sub.add_parser("edit")
    p_edit.add_argument("--index", type=int, required=True)
    p_edit.add_argument("--password", default=None)
    p_edit.add_argument("--website", default=None)
    p_remove = sub.add_parser("remove")
    p_remove.add_argument("--index", type=int, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command in (None, "list"):
            creds = auth.read_all_chaoxing_credentials()
            _write_json_line({"type": "ACCOUNTS",
                              "accounts": [{"index": c.get("index", i),
                                            "account": c.get("account", ""),
                                            "website": c.get("website") or ""}
                                           for i, c in enumerate(creds)]})
            return
        if args.command == "add":
            _cmd_add(args)
        elif args.command == "edit":
            _cmd_edit(args)
        elif args.command == "remove":
            _cmd_remove(args)
    except Exception as e:
        _write_json_line({"type": "ERROR", "error": str(e),
                          "detail": type(e).__name__})
        sys.exit(1)


if __name__ == "__main__":
    main()
