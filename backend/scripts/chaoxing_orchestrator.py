"""
Backward-compatible shim — legacy CLI entry for chaoxing_cli.ps1 / .bat.

All real logic lives in chaoxing/orchestrator.py. This file provides a
legacy-friendly ``main()`` that maps the old command-line flags to the current
``run_multi_account()`` API, so the PowerShell interactive CLI keeps working
without the JSON-line protocol (stdout remains the human-readable
``PROGRESS:[N] ...`` format parsed by chaoxing_cli.ps1).
"""

import argparse
import sys
from pathlib import Path

# Direct `python scripts/chaoxing_orchestrator.py` invocations put
# backend/scripts (not backend/) on sys.path; make the package importable.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from chaoxing.constants import OUTPUT_DIR  # noqa: E402
from chaoxing.logging_setup import log  # noqa: E402
from chaoxing.orchestrator import (  # noqa: E402
    run_for_account,
    process_course,
    ensure_logged_in,
    build_dynamic_course_config,
    discover_courses,
    save_discovered_state,
    run_multi_account,
    _run_account_in_thread,
)
from chaoxing.platform.auth import read_all_chaoxing_credentials  # noqa: E402
from chaoxing.tracking import ProgressTracker  # noqa: E402


def _print_status() -> None:
    """Print progress-tracker state for all persisted state files."""
    log("Progress tracker status")
    state_files = sorted(OUTPUT_DIR.glob("progress_state*.json"))
    if not state_files:
        log("  (no progress state files found)")
        return
    for state_path in state_files:
        tracker = ProgressTracker(state_file=state_path)
        state = tracker.state
        log(f"  {state_path.name}:")
        log(f"    completed courses: {len(state.get('completed_courses', []))}")
        log(f"    completed sections: {len(state.get('completed_sections', []))}")
        log(f"    errors: {len(state.get('errors', []))}")


def _resolve_account_indices(args) -> list[int]:
    all_creds = read_all_chaoxing_credentials()
    if args.all_accounts:
        return [c["index"] for c in all_creds] or [0]
    if args.account >= 0:
        return [args.account]
    return [0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chaoxing_orchestrator",
        description="Legacy Chaoxing automation CLI (backward-compatible shim).",
    )
    parser.add_argument("--status", action="store_true",
                        help="Print progress tracker state")
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--quiz-only", action="store_true")
    parser.add_argument("--content-only", action="store_true")
    parser.add_argument("--course", default=None)
    parser.add_argument("--account", type=int, default=-1)
    parser.add_argument("--all-accounts", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--yes", action="store_true",
                        help="Accepted for compatibility (the shim has no confirmation prompts)")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.status:
        _print_status()
        return

    all_creds = read_all_chaoxing_credentials()
    if not all_creds:
        log("No accounts found in passwords/chaoxing.txt", "ERROR")
        sys.exit(1)

    account_indices = _resolve_account_indices(args)
    if args.scan_only:
        mode = "scan_only"
    elif args.quiz_only:
        mode = "solve_only"
    else:
        mode = "full"

    log("=" * 60)
    log("Legacy CLI shim -> chaoxing.run_multi_account")
    log(f"mode={mode} accounts={account_indices} course={args.course or 'all'} "
        f"dry_run={args.dry_run} resume={args.resume} content_only={args.content_only}")
    log("=" * 60)

    run_multi_account(
        account_indices=account_indices,
        mode=mode,
        course=args.course,
        content_only=args.content_only,
        dry_run=args.dry_run,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
