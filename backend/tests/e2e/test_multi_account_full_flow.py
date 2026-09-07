"""
Multi-Account Full-Course E2E Test — headed Chrome, real browser automation.

Validates the refactored chaoxing/ backend by running the complete pipeline:
  Login → Course Discovery → Quiz Solving → Content Completion

Supports multi-account parallel execution with per-account JSON reports.

Usage:
    # Single account, scan only (safe, read-only)
    pytest tests/e2e/test_multi_account_full_flow.py -v -s --headed --scan-only

    # Single account, full run
    pytest tests/e2e/test_multi_account_full_flow.py -v -s --headed --accounts 0

    # All 3 accounts in parallel (spawns 3 headed Chrome windows)
    pytest tests/e2e/test_multi_account_full_flow.py -v -s --headed --all-accounts

    # Specific course only
    pytest tests/e2e/test_multi_account_full_flow.py -v -s --headed --accounts 0 --course "概率论"

    # Standalone (without pytest)
    python tests/e2e/test_multi_account_full_flow.py --headed --accounts 0 --scan-only

Design:
    - Uses chaoxing.orchestrator primitives directly (not legacy scripts/ path)
    - Thread-local session isolation per account (chaoxing-chrome-N)
    - JSON reports saved to output/e2e_reports/
    - Graceful Ctrl+C shutdown via SHUTDOWN_FLAG
    - Progress tracking + resume support
"""

import sys
import os
import json
import time
import threading
import argparse
import pytest
from pathlib import Path
from datetime import datetime

# Ensure project root on path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Chaoxing backend imports ──
from chaoxing.constants import WORKSPACE, OUTPUT_DIR, SHUTDOWN_FLAG
from chaoxing.config import load_config
from chaoxing.session import set_active_session
from chaoxing.logging_setup import log, progress
from chaoxing.platform.auth import (
    read_all_chaoxing_credentials,
    ensure_chaoxing_browser,
    chaoxing_login,
)
from chaoxing.orchestrator import (
    run_for_account,
    _parse_accounts_arg,
    ensure_logged_in,
    process_course,
    discover_courses,
    save_discovered_state,
)


# ═══════════════════════════════════════════════════════════════════════════
#  E2E Report Generation
# ═══════════════════════════════════════════════════════════════════════════

E2E_REPORT_DIR = OUTPUT_DIR / "e2e_reports"


def generate_e2e_report(account_index: int, creds: dict, args,
                         start_time: float, end_time: float,
                         courses_processed: list, errors: list) -> dict:
    """Generate a JSON report for a single account's E2E run."""
    elapsed_min = (end_time - start_time) / 60.0
    report = {
        "test_run": {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "account_index": account_index,
            "account_masked": f"{creds['account'][:3]}***",
            "mode": "scan_only" if args.scan_only else (
                "dry_run" if args.dry_run else "live"
            ),
            "headed": getattr(args, 'headed', False),
            "elapsed_minutes": round(elapsed_min, 1),
        },
        "courses": courses_processed,
        "errors": errors,
        "summary": {
            "total_courses": len(courses_processed),
            "courses_with_quizzes": sum(
                1 for c in courses_processed if c.get("quiz_sections", 0) > 0),
            "courses_with_content": sum(
                1 for c in courses_processed if c.get("content_sections", 0) > 0),
            "error_count": len(errors),
            "success": len(errors) == 0,
        },
    }
    return report


def save_e2e_report(account_index: int, report: dict):
    """Save E2E report JSON to output/e2e_reports/."""
    E2E_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"e2e_account{account_index}_{ts}.json"
    filepath = E2E_REPORT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"E2E report saved: {filepath}")
    return filepath


# ═══════════════════════════════════════════════════════════════════════════
#  E2E Per-Account Runner (wraps orchestrator primitives with reporting)
# ═══════════════════════════════════════════════════════════════════════════

def e2e_run_for_account(account_index: int, creds: dict, args) -> dict:
    """Run full E2E pipeline for one account with timing and error capture.

    Returns a report dict suitable for JSON serialization.
    """
    session_name = f"chaoxing-chrome-{account_index}"
    set_active_session(session_name)

    courses_processed = []
    errors = []
    start_time = time.time()

    log(f"\n{'='*60}")
    log(f"E2E TEST — Account [{account_index}]: {creds['account'][:3]}***")
    log(f"Session: {session_name}")
    log(f"Mode: {'HEADED' if getattr(args, 'headed', False) else 'HEADLESS'}")
    log(f"{'='*60}")

    # ── Step 1: Open browser & login ──
    try:
        log(f"[E2E:{account_index}] Step 1: Opening browser & logging in...")
        progress(account_index, "Opening browser...")

        if not ensure_chaoxing_browser(account_index):
            raise RuntimeError(f"Failed to open browser for account {account_index}")

        if not ensure_logged_in(account_index):
            raise RuntimeError(f"Login failed for account {account_index}")

        progress(account_index, "Logged in ✓")
        log(f"[E2E:{account_index}] ✅ Login successful")
    except Exception as e:
        log(f"[E2E:{account_index}] ❌ Login/browser error: {e}", "ERROR")
        errors.append({"step": "login", "error": str(e)})
        end_time = time.time()
        return generate_e2e_report(
            account_index, creds, args, start_time, end_time, [], errors)

    # ── Step 2: Discover courses ──
    try:
        log(f"[E2E:{account_index}] Step 2: Discovering courses...")
        progress(account_index, "Scanning courses...")

        dynamic_courses = discover_courses(
            getattr(args, 'course', None))
        save_discovered_state(dynamic_courses)

        if not dynamic_courses:
            log(f"[E2E:{account_index}] ℹ️  No unfinished courses found "
                f"(all complete or none available)")
            progress(account_index, "No unfinished courses")

        progress(account_index, f"Found {len(dynamic_courses)} course(s)")
        log(f"[E2E:{account_index}] ✅ Discovered {len(dynamic_courses)} course(s)")
        for c in dynamic_courses:
            q_count = len(c.get("remaining_quiz_sections", []))
            ch_count = len(c.get("chapters", []))
            log(f"    {c['name']}: {c.get('current_progress', '?')}/"
                f"{c.get('total_tasks', '?')} "
                f"[Quiz×{q_count}] [Content×{ch_count}]")
    except Exception as e:
        log(f"[E2E:{account_index}] ❌ Discovery error: {e}", "ERROR")
        errors.append({"step": "discovery", "error": str(e)})
        end_time = time.time()
        return generate_e2e_report(
            account_index, creds, args, start_time, end_time, [], errors)

    # ── Step 3: Process courses ──
    if args.scan_only:
        log(f"[E2E:{account_index}] ℹ️  Scan-only mode — skipping course processing")
        for c in dynamic_courses:
            courses_processed.append({
                "name": c.get("name", "?"),
                "courseid": c.get("courseid", "?"),
                "progress": f"{c.get('current_progress', '?')}/"
                            f"{c.get('total_tasks', '?')}",
                "quiz_sections": len(c.get("remaining_quiz_sections", [])),
                "content_sections": len(c.get("chapters", [])),
                "status": "scanned",
            })
        progress(account_index, f"Scan complete — {len(dynamic_courses)} courses")
    else:
        total = len(dynamic_courses)
        for i, course in enumerate(dynamic_courses):
            if SHUTDOWN_FLAG.is_set():
                log(f"[E2E:{account_index}] ⚠️  Shutdown flag set, "
                    f"stopping course processing", "WARN")
                save_discovered_state(dynamic_courses)
                break

            name = course.get("name", "?")
            progress(account_index, f"Processing: {name}", i + 1, total)

            course_start = time.time()
            course_error = None
            try:
                process_course(
                    course,
                    dry_run=getattr(args, 'dry_run', False),
                    quiz_only=getattr(args, 'quiz_only', False),
                    content_only=getattr(args, 'content_only', False),
                )
                status = "completed"
            except KeyboardInterrupt:
                log(f"\n[E2E:{account_index}] Interrupted during {name}", "WARN")
                save_discovered_state(dynamic_courses)
                status = "interrupted"
                break
            except Exception as e:
                log(f"[E2E:{account_index}] ❌ Error processing {name}: {e}", "ERROR")
                import traceback
                traceback.print_exc()
                course_error = str(e)
                status = "error"
                errors.append({
                    "step": f"process_course:{name}",
                    "error": str(e),
                })

            course_elapsed = time.time() - course_start
            courses_processed.append({
                "name": name,
                "courseid": course.get("courseid", "?"),
                "quiz_sections": len(course.get("remaining_quiz_sections", [])),
                "content_sections": len(course.get("chapters", [])),
                "status": status,
                "elapsed_minutes": round(course_elapsed / 60.0, 1),
                "error": course_error,
            })

            progress(account_index,
                     f"{'✓' if status == 'completed' else '✗'} {name}",
                     i + 1, total)

    end_time = time.time()
    report = generate_e2e_report(
        account_index, creds, args, start_time, end_time,
        courses_processed, errors)

    # ── Print summary ──
    elapsed = report["test_run"]["elapsed_minutes"]
    log(f"\n[E2E:{account_index}] {'='*60}")
    log(f"[E2E:{account_index}] FINISHED in {elapsed:.1f} min")
    log(f"[E2E:{account_index}] Courses: {len(courses_processed)}")
    log(f"[E2E:{account_index}] Errors: {len(errors)}")
    log(f"[E2E:{account_index}] {'='*60}")

    save_e2e_report(account_index, report)
    return report


# ═══════════════════════════════════════════════════════════════════════════
#  Multi-Account Thread Runner
# ═══════════════════════════════════════════════════════════════════════════

# Thread-safe collector for per-account reports
_report_lock = threading.Lock()
_all_reports: list = []


def _e2e_thread_target(account_index: int, creds: dict, args):
    """Thread target for multi-account E2E testing."""
    tname = f"e2e-account-{account_index}"
    threading.current_thread().name = tname
    try:
        if SHUTDOWN_FLAG.is_set():
            log(f"[E2E] Shutdown flag set, skipping account {account_index}", "WARN")
            return
        report = e2e_run_for_account(account_index, creds, args)
        with _report_lock:
            _all_reports.append(report)
    except KeyboardInterrupt:
        log(f"[E2E] Interrupted — account {account_index}", "WARN")
        SHUTDOWN_FLAG.set()
    except Exception as e:
        log(f"[E2E] Fatal error in thread for account {account_index}: {e}", "ERROR")
        import traceback as _tb
        _tb.print_exc()


def e2e_run_multi_account(accounts: list, args) -> list:
    """Run E2E test for multiple accounts in parallel threads.

    Args:
        accounts: List of credential dicts from read_all_chaoxing_credentials()
        args: argparse.Namespace with test parameters

    Returns:
        List of per-account report dicts
    """
    global _all_reports
    _all_reports = []

    SHUTDOWN_FLAG.clear()

    log(f"\n{'#'*60}")
    log(f"# E2E Multi-Account Test — {len(accounts)} account(s)")
    log(f"# Mode: {'HEADED' if getattr(args, 'headed', False) else 'HEADLESS'}")
    log(f"# Scan-only: {args.scan_only}")
    log(f"# Dry-run: {getattr(args, 'dry_run', False)}")
    log(f"{'#'*60}\n")

    threads = []
    for cred in accounts:
        t = threading.Thread(
            target=_e2e_thread_target,
            args=(cred["index"], cred, args),
            name=f"e2e-account-{cred['index']}",
            daemon=True,
        )
        t.start()
        threads.append(t)
        log(f"[E2E] Started thread for account [{cred['index']}] "
            f"({cred['account'][:3]}***)")
        # Stagger to avoid simultaneous browser launches
        time.sleep(1.5)

    # Wait for all threads
    try:
        for t in threads:
            while t.is_alive():
                t.join(timeout=1.0)
    except KeyboardInterrupt:
        log("\n[E2E] Ctrl+C — signaling all threads to stop...", "WARN")
        SHUTDOWN_FLAG.set()
        for t in threads:
            t.join(timeout=10.0)
        log("[E2E] All threads stopped.")

    # ── Aggregate summary ──
    log(f"\n{'#'*60}")
    log(f"# E2E MULTI-ACCOUNT SUMMARY")
    log(f"{'#'*60}")
    for report in _all_reports:
        tr = report["test_run"]
        s = report["summary"]
        status_icon = "✅" if s["success"] else "❌"
        log(f"  {status_icon} Account [{tr['account_index']}] "
            f"({tr['account_masked']}): "
            f"{s['total_courses']} courses, "
            f"{s['error_count']} errors, "
            f"{tr['elapsed_minutes']:.1f} min")

    # Save aggregate report
    aggregate = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_accounts": len(accounts),
        "accounts_tested": len(_all_reports),
        "mode": "scan_only" if args.scan_only else (
            "dry_run" if getattr(args, 'dry_run', False) else "live"),
        "headed": getattr(args, 'headed', False),
        "per_account": _all_reports,
        "overall_success": all(
            r["summary"]["success"] for r in _all_reports),
    }
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    agg_path = E2E_REPORT_DIR / f"e2e_aggregate_{ts}.json"
    with open(agg_path, "w", encoding="utf-8") as f:
        json.dump(aggregate, f, ensure_ascii=False, indent=2)
    log(f"\nAggregate report saved: {agg_path}")

    return _all_reports


# ═══════════════════════════════════════════════════════════════════════════
#  Pytest Integration
# ═══════════════════════════════════════════════════════════════════════════

def pytest_addoption(parser):
    """Add E2E-specific CLI options to pytest."""
    parser.addoption(
        "--headed", action="store_true", default=False,
        help="Run with headed (visible) Chrome browsers"
    )
    parser.addoption(
        "--accounts", type=str, default=None,
        help="Comma-separated account indices (e.g. 0,1,2)"
    )
    parser.addoption(
        "--all-accounts", action="store_true", default=False,
        help="Run all accounts from passwords/chaoxing.txt in parallel"
    )
    parser.addoption(
        "--course", type=str, default=None,
        help="Filter courses by name (substring match)"
    )
    parser.addoption(
        "--scan-only", action="store_true", default=False,
        help="Only scan and report courses (no submissions)"
    )
    parser.addoption(
        "--dry-run", action="store_true", default=False,
        help="Preview mode — no actual submissions"
    )
    parser.addoption(
        "--quiz-only", action="store_true", default=False,
        help="Only process quiz sections"
    )
    parser.addoption(
        "--content-only", action="store_true", default=False,
        help="Only process content sections"
    )


@pytest.fixture(scope="module")
def e2e_args(request):
    """Build an argparse.Namespace from pytest CLI options for E2E tests."""
    args = argparse.Namespace()
    args.headed = request.config.getoption("--headed", default=False)
    args.accounts = request.config.getoption("--accounts", default=None)
    args.all_accounts = request.config.getoption("--all-accounts", default=False)
    args.account = None
    args.course = request.config.getoption("--course", default=None)
    args.scan_only = request.config.getoption("--scan-only", default=False)
    args.dry_run = request.config.getoption("--dry-run", default=False)
    args.quiz_only = request.config.getoption("--quiz-only", default=False)
    args.content_only = request.config.getoption("--content-only", default=False)
    args.resume = False
    args.yes = True  # Non-interactive in test mode
    args.status = False
    return args


# ═══════════════════════════════════════════════════════════════════════════
#  Test Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiAccountE2E:
    """Multi-account full-course E2E tests.

    All tests require --run-e2e flag + --headed for real browser testing.
    These tests use real Chaoxing accounts and make real submissions.
    """

    @pytest.mark.skip(reason="E2E test — run manually with: "
                      "pytest tests/e2e/test_multi_account_full_flow.py -v -s "
                      "--headed --scan-only --accounts 0 --run-e2e")
    def test_single_account_scan(self, e2e_args):
        """Scan courses for a single account (read-only, safe)."""
        # Override for scan-only
        e2e_args.scan_only = True
        e2e_args.accounts = e2e_args.accounts or "0"

        # Set headed mode
        if e2e_args.headed:
            os.environ["CHAOXING_HEADED"] = "1"

        all_creds = read_all_chaoxing_credentials()
        assert all_creds, "No credentials found in passwords/chaoxing.txt"

        accounts = _parse_accounts_arg(e2e_args, all_creds)
        assert accounts, f"No accounts matched: {e2e_args.accounts}"

        reports = e2e_run_multi_account(accounts, e2e_args)
        assert len(reports) > 0, "No reports generated"

        for report in reports:
            assert report["summary"]["error_count"] == 0, \
                f"Account {report['test_run']['account_index']} had errors: " \
                f"{report['errors']}"

    @pytest.mark.skip(reason="E2E test — run manually with: "
                      "pytest tests/e2e/test_multi_account_full_flow.py -v -s "
                      "--headed --all-accounts --scan-only --run-e2e")
    def test_all_accounts_scan(self, e2e_args):
        """Scan courses for ALL accounts in parallel (read-only, safe)."""
        e2e_args.scan_only = True
        e2e_args.all_accounts = True

        if e2e_args.headed:
            os.environ["CHAOXING_HEADED"] = "1"

        all_creds = read_all_chaoxing_credentials()
        assert all_creds, "No credentials found"

        reports = e2e_run_multi_account(all_creds, e2e_args)
        assert len(reports) == len(all_creds), \
            f"Expected {len(all_creds)} reports, got {len(reports)}"

        for report in reports:
            assert report["summary"]["error_count"] == 0, \
                f"Account {report['test_run']['account_index']} had scan errors"


# ═══════════════════════════════════════════════════════════════════════════
#  Standalone entry point (python tests/e2e/test_multi_account_full_flow.py)
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Chaoxing Multi-Account E2E Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tests/e2e/test_multi_account_full_flow.py --headed --scan-only
  python tests/e2e/test_multi_account_full_flow.py --headed --accounts 0 --scan-only
  python tests/e2e/test_multi_account_full_flow.py --headed --all-accounts --scan-only
  python tests/e2e/test_multi_account_full_flow.py --headed --accounts 0 --course "概率论"
  python tests/e2e/test_multi_account_full_flow.py --headed --all-accounts
        """
    )
    parser.add_argument("--headed", action="store_true", default=True,
                        help="Run with headed (visible) Chrome (default: True)")
    parser.add_argument("--headless", action="store_true", default=False,
                        help="Run headless (override default headed)")
    parser.add_argument("--accounts", type=str, default=None,
                        help="Comma-separated account indices (e.g. 0,1,2)")
    parser.add_argument("--all-accounts", action="store_true", default=False,
                        help="Run ALL accounts in parallel")
    parser.add_argument("--account", type=int, default=None,
                        help="Single account index")
    parser.add_argument("--course", type=str, default=None,
                        help="Filter courses by name (substring match)")
    parser.add_argument("--scan-only", action="store_true", default=False,
                        help="Only scan courses (read-only, no submissions)")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Preview mode — no actual submissions")
    parser.add_argument("--quiz-only", action="store_true", default=False,
                        help="Only process quiz sections")
    parser.add_argument("--content-only", action="store_true", default=False,
                        help="Only process content sections")
    parser.add_argument("--yes", action="store_true", default=True,
                        help="Skip confirmations (default: True for automated tests)")

    args = parser.parse_args()

    # Headed by default unless --headless is explicitly passed
    if args.headless:
        args.headed = False
        if "CHAOXING_HEADED" in os.environ:
            del os.environ["CHAOXING_HEADED"]
    else:
        args.headed = True
        os.environ["CHAOXING_HEADED"] = "1"

    # Build account list
    if args.all_accounts:
        args.accounts = None
        args.account = None

    # Ensure output dirs exist
    E2E_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Read credentials
    all_creds = read_all_chaoxing_credentials()
    if not all_creds:
        log("❌ No accounts found in passwords/chaoxing.txt", "ERROR")
        sys.exit(1)

    log(f"Found {len(all_creds)} account(s) in passwords/chaoxing.txt")

    # Determine which accounts to run
    if args.all_accounts:
        accounts = all_creds
        log(f"Running ALL {len(accounts)} accounts in parallel")
    elif args.accounts or args.account is not None:
        accounts = _parse_accounts_arg(args, all_creds)
    else:
        # Default: single account 0
        accounts = [all_creds[0]]
        log("Defaulting to account [0]")

    if not accounts:
        log("❌ No accounts selected", "ERROR")
        sys.exit(1)

    # ── Safety warning for live mode ──
    if not args.scan_only and not args.dry_run:
        log("")
        log("⚠️  ==============================================", "WARN")
        log("⚠️  LIVE MODE — real quiz submissions will be made", "WARN")
        log("⚠️  ==============================================", "WARN")
        log("")
        if not args.yes:
            try:
                confirm = input("Proceed? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                log("Aborted.", "WARN")
                sys.exit(0)
            if confirm != 'y':
                log("Aborted by user.", "WARN")
                sys.exit(0)

    # ── Run ──
    reports = e2e_run_multi_account(accounts, args)

    # ── Exit code ──
    all_ok = all(r["summary"]["success"] for r in reports)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
