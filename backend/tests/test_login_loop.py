"""
Repeated login test — measures chaoxing_login() reliability over N attempts.

Usage:
    python test_login_loop.py           # Run 10 attempts (default)
    python test_login_loop.py -n 5      # Run 5 attempts
"""
import sys
import time
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from utils import (
    cfg, log,
    pw_snapshot, pw_goto, pw_run_code_file, pw_extract_result,
    read_chaoxing_credentials, chaoxing_login,
    ensure_chaoxing_browser, is_chaoxing_browser_open,
)

SCRIPT_DIR = Path(__file__).parent.parent / "scripts"


def logout_chaoxing() -> bool:
    """Log out of Chaoxing so we can re-test login."""
    logout_js = """
    async (page) => {
        // Try the logout URL first
        await page.goto('https://passport2.chaoxing.com/logout', {waitUntil: 'domcontentloaded'});
        await page.waitForTimeout(3000);

        const title = await page.title();
        const url = page.url();

        // Also clear relevant cookies for extra safety
        // Navigation to login page should trigger re-auth
        await page.goto('https://passport2.chaoxing.com/login?fid=&newversion=true&refer=https%3A%2F%2Fi.chaoxing.com', {waitUntil: 'domcontentloaded'});
        await page.waitForTimeout(2000);

        return JSON.stringify({
            loggedOut: !url.includes('i.chaoxing.com/base'),
            loginPageLoaded: page.url().includes('passport2.chaoxing.com'),
            title: await page.title(),
        });
    }
    """
    import tempfile
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.js', delete=False,
        dir=str(SCRIPT_DIR), encoding='utf-8')
    tmp.write(logout_js)
    tmp.close()
    try:
        raw = pw_run_code_file(tmp.name, timeout=30)
        result_str = pw_extract_result(raw)
        result = json.loads(result_str)
        log(f"  Logout result: {json.dumps(result, ensure_ascii=False)}")
        return result.get('loggedOut', True)
    except Exception as e:
        log(f"  Logout error: {e}", "ERROR")
        return False
    finally:
        try: os.unlink(tmp.name)
        except: pass


def single_login_test() -> dict:
    """Perform one login attempt and return timing/result info."""
    start = time.time()
    success = chaoxing_login()
    elapsed = time.time() - start
    return {
        "success": success,
        "elapsed_sec": round(elapsed, 2),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=10, help="Number of attempts")
    args = parser.parse_args()

    N = args.n
    log(f"{'='*60}")
    log(f"Chaoxing Login Reliability Test — {N} attempts")
    log(f"{'='*60}")

    # Ensure browser is open
    if not ensure_chaoxing_browser():
        log("Cannot open browser — aborting", "ERROR")
        return

    # Read credentials (just to verify they exist)
    creds = read_chaoxing_credentials()
    if not creds:
        log("No credentials — aborting", "ERROR")
        return

    results = []
    for i in range(1, N + 1):
        log(f"\n{'─'*40}")
        log(f"Attempt {i}/{N}")

        # Log out first to ensure a fresh login test
        log(f"  Logging out...")
        logout_chaoxing()
        time.sleep(1)

        # Test login
        result = single_login_test()
        results.append(result)

        status = "✅ PASS" if result["success"] else "❌ FAIL"
        log(f"  {status} in {result['elapsed_sec']}s")

        if i < N:
            time.sleep(1)

    # ── Summary ──
    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    success_rate = len(successes) / N * 100
    avg_time = sum(r["elapsed_sec"] for r in results) / N

    log(f"\n{'='*60}")
    log(f"RESULTS: {len(successes)}/{N} passed ({success_rate:.0f}%)")
    log(f"  Average time: {avg_time:.1f}s")
    if successes:
        times = [r["elapsed_sec"] for r in successes]
        log(f"  Fastest: {min(times):.1f}s  Slowest: {max(times):.1f}s  Median: {sorted(times)[len(times)//2]:.1f}s")
    if failures:
        log(f"  Failures: {len(failures)}/{N}")
    log(f"{'='*60}")


if __name__ == "__main__":
    main()
