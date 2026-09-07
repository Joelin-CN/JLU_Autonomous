"""
CLI entry point for listing discovered courses for one account.

Usage::

    python -m chaoxing.courses --account 0

Emits exactly ONE line of JSON to stdout for the frontend to consume:

    success: {"type":"COURSES","scanned":true,"courses":[{...}, ...]}
    empty:   {"type":"COURSES","scanned":false,"courses":[]}        (no scan yet)
    failure: {"type":"ERROR","error":"<msg>","detail":"<type>"}  + exit code 1

This command reads the discovery state that a prior ``scan_only`` job persisted
via ``discover.save_discovered_state()`` — it does NOT scan the platform itself
(that requires a logged-in browser session and runs through ``chaoxing.api``).

Account N maps to session ``chaoxing-chrome-N`` (see orchestrator.run_for_account),
whose discovery file is ``output/discovered_courses_chaoxing-chrome-N.json``. A
legacy single-account run with the default session writes the un-suffixed
``output/discovered_courses.json``, so we fall back to that.

When no discovery file exists yet (the user hasn't run a scan), this is NOT an
error: we return an empty list with ``scanned: false`` so the UI can show a
friendly "请先扫描" hint instead of a red error.

All debug output goes to stderr; stdout is strictly one JSON line.
"""

import sys
import json
import argparse

from .constants import OUTPUT_DIR


def _write_json_line(obj: dict) -> None:
    """Write a single compact JSON object as one line to stdout, then flush."""
    line = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _discovered_file(account_index: int):
    """Resolve the discovery file for an account, preferring the per-session
    name and falling back to the legacy un-suffixed file. Returns the first
    Path that exists, or None.
    """
    session = f"chaoxing-chrome-{account_index}"
    candidates = [
        OUTPUT_DIR / f"discovered_courses_{session}.json",
        OUTPUT_DIR / "discovered_courses.json",  # legacy / default-session run
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _derive_status(done: int, total: int) -> str:
    """Map progress counts to the renderer's course status vocabulary."""
    if total > 0 and done >= total:
        return "completed"
    if done > 0:
        return "in_progress"
    return "not_started"


def _map_course(raw: dict, account_index: int) -> dict:
    """Map a discovered-course config dict (build_dynamic_course_config shape)
    to the electron Course shape that course.handler.ts forwards to the UI.

    Source fields (discover.build_dynamic_course_config):
      name, courseid, clazzid, cpi, current_progress, total_tasks,
      remaining_quiz_sections, remaining_content_sections, chapters
    """
    done = int(raw.get("current_progress", 0) or 0)
    total = int(raw.get("total_tasks", 0) or 0)
    # Guard against malformed data where done somehow exceeds total.
    if total > 0:
        done = min(done, total)
    progress = round(done / total * 100) if total > 0 else 0
    course_id = str(raw.get("courseid", ""))

    return {
        # id must be unique per account so multiple accounts' courses don't
        # collide in the renderer's flat course list.
        "id": f"{account_index}:{course_id}" if course_id else f"{account_index}:{raw.get('name', '')}",
        "name": raw.get("name", ""),
        "accountId": account_index,
        "courseId": course_id,
        "classId": str(raw.get("clazzid", "")),
        "progress": progress,
        "status": _derive_status(done, total),
        # Explicit counts — course.handler / mapElectronCourse use these
        # directly rather than deriving from a synthetic sections array.
        "totalSections": total,
        "completedSections": done,
    }


def main() -> None:
    """Read discovered courses for one account and emit a single JSON line.

    Exits 0 on success (COURSES, possibly empty), 1 on failure (ERROR).
    """
    parser = argparse.ArgumentParser(prog="chaoxing.courses", add_help=True)
    parser.add_argument(
        "--account", type=int, default=0,
        help="0-based account index (maps to session chaoxing-chrome-N)",
    )
    args = parser.parse_args()

    try:
        path = _discovered_file(args.account)
        if path is None:
            # No scan has been run for this account yet — friendly empty result.
            _write_json_line({"type": "COURSES", "scanned": False, "courses": []})
            return

        with open(path, "r", encoding="utf-8") as f:
            raw_courses = json.load(f)

        if not isinstance(raw_courses, list):
            raise ValueError(f"discovered file is not a JSON array: {path.name}")

        courses = [_map_course(c, args.account) for c in raw_courses if isinstance(c, dict)]
        _write_json_line({"type": "COURSES", "scanned": True, "courses": courses})

    except Exception as e:
        _write_json_line({
            "type": "ERROR",
            "error": str(e),
            "detail": type(e).__name__,
        })
        sys.exit(1)


if __name__ == "__main__":
    main()
