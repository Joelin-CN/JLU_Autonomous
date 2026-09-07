"""Tests for playwright-cli availability guards (friendly missing-CLI errors)."""
import subprocess
from unittest.mock import patch, MagicMock

import pytest

import chaoxing.browser.engine as engine
from chaoxing.browser.engine import (
    PlaywrightCliMissingError,
    ensure_cli_available,
    pw,
)
import chaoxing.platform.auth as auth


@pytest.fixture(autouse=True)
def _clear_cache():
    engine._CLI_AVAILABILITY_CACHE.clear()
    yield
    engine._CLI_AVAILABILITY_CACHE.clear()


class TestEnsureCliAvailable:
    """ensure_cli_available() raises a friendly error when the CLI is absent."""

    def test_missing_cli_raises_with_guidance(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(PlaywrightCliMissingError) as ei:
                ensure_cli_available("playwright-cli.cmd")
        msg = str(ei.value)
        assert "playwright-cli" in msg
        assert "npm install -g playwright-cli" in msg

    def test_present_cli_passes_and_caches(self):
        calls = []

        def fake_which(name):
            calls.append(name)
            return "C:/npm/" + name

        with patch("shutil.which", side_effect=fake_which):
            ensure_cli_available("playwright-cli.cmd")
            ensure_cli_available("playwright-cli.cmd")
        assert len(calls) == 1, "second check must hit the cache"

    def test_cmd_suffix_falls_back_to_bare_name(self):
        # Configured as .cmd but only the bare name resolves (non-Windows style)
        def fake_which(name):
            return "C:/npm/playwright-cli" if name == "playwright-cli" else None

        with patch("shutil.which", side_effect=fake_which):
            ensure_cli_available("playwright-cli.cmd")  # must not raise


class TestPwGuard:
    """pw() converts a missing CLI into the friendly error."""

    def test_pw_raises_friendly_when_missing(self):
        with patch("shutil.which", return_value=None), \
             patch("chaoxing.config.cfg", return_value="no-such-cli.cmd"):
            with pytest.raises(PlaywrightCliMissingError):
                pw("snapshot")

    def test_pw_detects_not_recognized_stderr(self):
        # shell=True path: cmd.exe prints "not recognized" instead of
        # raising FileNotFoundError.
        engine._CLI_AVAILABILITY_CACHE.add("playwright-cli.cmd")
        result = MagicMock(
            returncode=1, stdout="",
            stderr="'playwright-cli.cmd' is not recognized as an internal or external command")
        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"), \
             patch("chaoxing.browser.engine.subprocess.run", return_value=result):
            with pytest.raises(PlaywrightCliMissingError):
                pw("snapshot", use_shell=True)


class TestAuthGuards:
    """auth.py surfaces the friendly error instead of WinError 2."""

    def test_is_open_raises_friendly_on_file_not_found(self):
        with patch("chaoxing.config.cfg", return_value="no-such-cli.cmd"), \
             patch("shutil.which", return_value=None), \
             patch.object(auth, "_get_active_session", return_value="s-x"):
            with pytest.raises(PlaywrightCliMissingError):
                auth.is_chaoxing_browser_open()

    def test_close_logs_friendly_warning(self):
        with patch("chaoxing.config.cfg", return_value="no-such-cli.cmd"), \
             patch("chaoxing.platform.auth.subprocess.run",
                   side_effect=FileNotFoundError("winerror 2")), \
             patch("chaoxing.platform.auth.log") as mock_log:
            ok = auth.close_chaoxing_browser(0)
        assert ok is False
        logged = " ".join(str(c.args[0]) for c in mock_log.call_args_list)
        assert "npm install -g playwright-cli" in logged


class TestPwTimeoutRecovery:
    """pw() retries a timed-out command, then rebuilds the session."""

    def test_transient_timeout_recovered_by_retry(self):
        calls = []

        def fake_run(*a, **kw):
            calls.append(1)
            if len(calls) == 1:
                raise subprocess.TimeoutExpired(cmd="pw", timeout=15)
            return MagicMock(returncode=0, stdout="ok", stderr="")

        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"),              patch("shutil.which", return_value="C:/x/playwright-cli.cmd"),              patch.object(engine, "_get_active_session", return_value="chaoxing-chrome-0"),              patch("chaoxing.browser.engine.subprocess.run", side_effect=fake_run),              patch("chaoxing.browser.engine.time.sleep"):
            out = pw("snapshot")
        assert out == "ok"
        assert len(calls) == 2

    def _unused_transient(self, calls, fake_run):

        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"), \
             patch("shutil.which", return_value="C:/x/playwright-cli.cmd"), \
             patch.object(engine, "_get_active_session", return_value="chaoxing-chrome-0"), \
             patch("chaoxing.browser.engine.subprocess.run", side_effect=fake_run), \
             patch("chaoxing.browser.engine.time.sleep"):
            out = pw("snapshot")
        assert out == "ok"
        assert len(calls) == 2

    def test_persistent_timeout_triggers_rebuild_and_third_try(self):
        attempts = []

        def fake_run(*a, **kw):
            attempts.append(a)
            if len(attempts) <= 2:
                raise subprocess.TimeoutExpired(cmd="pw", timeout=15)
            # third call is the post-rebuild retry
            return MagicMock(returncode=0, stdout="recovered", stderr="")

        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"), \
             patch("shutil.which", return_value="C:/x/playwright-cli.cmd"), \
             patch.object(engine, "_get_active_session", return_value="chaoxing-chrome-0"), \
             patch("chaoxing.browser.engine.subprocess.run", side_effect=fake_run), \
             patch("chaoxing.browser.engine.time.sleep"), \
             patch.object(engine, "_rebuild_session") as mock_rebuild:
            out = pw("run-code", "async (page) => 1")
        assert out == "recovered"
        assert mock_rebuild.call_count == 1
        assert mock_rebuild.call_args[0][0] == "chaoxing-chrome-0"

    def test_all_timeouts_raise_after_rebuild(self):
        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"), \
             patch("shutil.which", return_value="C:/x/playwright-cli.cmd"), \
             patch.object(engine, "_get_active_session", return_value="chaoxing-chrome-0"), \
             patch("chaoxing.browser.engine.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="pw", timeout=15)), \
             patch("chaoxing.browser.engine.time.sleep"), \
             patch.object(engine, "_rebuild_session"):
            with pytest.raises(subprocess.TimeoutExpired):
                pw("snapshot")

    def test_missing_cli_error_not_retried(self):
        from chaoxing.browser.engine import PlaywrightCliMissingError
        with patch("chaoxing.config.cfg", return_value="no-such-cli.cmd"), \
             patch("shutil.which", return_value=None):
            with pytest.raises(PlaywrightCliMissingError):
                pw("snapshot")


class TestPwSessionDeadRecovery:
    """pw() recovers when the daemon reports its browser target died."""

    def test_browser_closed_error_triggers_retry_then_success(self):
        from chaoxing.browser.engine import SessionDeadError
        calls = []

        def fake_run(*a, **kw):
            calls.append(1)
            if len(calls) == 1:
                r = MagicMock(returncode=1, stdout="",
                              stderr="Error: Target page, context or browser has been closed")
                return r
            return MagicMock(returncode=0, stdout="ok", stderr="")

        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"), \
             patch("shutil.which", return_value="C:/x/playwright-cli.cmd"), \
             patch.object(engine, "_get_active_session", return_value="chaoxing-chrome-0"), \
             patch("chaoxing.browser.engine.subprocess.run", side_effect=fake_run), \
             patch("chaoxing.browser.engine.time.sleep"):
            out = pw("run-code", "async (page) => 1")
        assert out == "ok"
        assert len(calls) == 2

    def test_browser_closed_persistent_triggers_rebuild(self):
        attempts = []

        def fake_run(*a, **kw):
            attempts.append(1)
            if len(attempts) <= 2:
                return MagicMock(returncode=1, stdout="",
                                 stderr="Error: Browser has been disconnected")
            return MagicMock(returncode=0, stdout="recovered", stderr="")

        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"), \
             patch("shutil.which", return_value="C:/x/playwright-cli.cmd"), \
             patch.object(engine, "_get_active_session", return_value="chaoxing-chrome-3"), \
             patch("chaoxing.browser.engine.subprocess.run", side_effect=fake_run), \
             patch("chaoxing.browser.engine.time.sleep"), \
             patch.object(engine, "_rebuild_session") as mock_rebuild:
            out = pw("click", "e12")
        assert out == "recovered"
        assert mock_rebuild.call_args[0][0] == "chaoxing-chrome-3"

    def test_ordinary_rc1_stderr_not_treated_as_dead(self):
        # A plain failure must NOT enter the rebuild path — it just warns
        # and returns stdout, preserving the old behavior.
        result = MagicMock(returncode=1, stdout="partial", stderr="some other error")
        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"), \
             patch("shutil.which", return_value="C:/x/playwright-cli.cmd"), \
             patch.object(engine, "_get_active_session", return_value="chaoxing-chrome-0"), \
             patch("chaoxing.browser.engine.subprocess.run", return_value=result), \
             patch.object(engine, "_rebuild_session") as mock_rebuild:
            out = pw("snapshot")
        assert out == "partial"
        assert mock_rebuild.call_count == 0


class TestPwStdoutDeadMarker:
    """The CLI reports dead browsers on STDOUT with rc=0 — still recover."""

    def test_stdout_error_marker_with_rc0_triggers_recovery(self):
        calls = []

        def fake_run(*a, **kw):
            calls.append(1)
            if len(calls) == 1:
                return MagicMock(returncode=0,
                                 stdout="### Error\nError: Target page, context or browser has been closed",
                                 stderr="")
            return MagicMock(returncode=0, stdout="ok", stderr="")

        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"), \
             patch("shutil.which", return_value="C:/x/playwright-cli.cmd"), \
             patch.object(engine, "_get_active_session", return_value="chaoxing-chrome-0"), \
             patch("chaoxing.browser.engine.subprocess.run", side_effect=fake_run), \
             patch("chaoxing.browser.engine.time.sleep"):
            out = pw("run-code", "--filename=x.js")
        assert out == "ok"
        assert len(calls) == 2

    def test_normal_result_stdout_not_misdetected(self):
        r = MagicMock(returncode=0, stdout="### Result\n\"clicked:1.3\"", stderr="")
        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"), \
             patch("shutil.which", return_value="C:/x/playwright-cli.cmd"), \
             patch.object(engine, "_get_active_session", return_value="chaoxing-chrome-0"), \
             patch("chaoxing.browser.engine.subprocess.run", return_value=r), \
             patch.object(engine, "_rebuild_session") as mock_rebuild:
            out = pw("click", "e1")
        assert "clicked" in out
        assert mock_rebuild.call_count == 0


class TestPwNotOpenStderr:
    """Daemon-deregistered session: rc=1, stderr "Browser ... is not open"."""

    def test_not_open_stderr_triggers_recovery(self):
        calls = []
        stderr_blob = (
            "C:\...\session.js:60\n"
            "      throw new Error(`Browser '${'x'}' is not open. Run`\n"
            "Error: Browser 'chaoxing-chrome-0' is not open. Run\n"
            "  playwright-cli -s=chaoxing-chrome-0 open\n"
        )

        def fake_run(*a, **kw):
            calls.append(1)
            if len(calls) == 1:
                return MagicMock(returncode=1, stdout="", stderr=stderr_blob)
            return MagicMock(returncode=0, stdout="ok", stderr="")

        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"), \
             patch("shutil.which", return_value="C:/x/playwright-cli.cmd"), \
             patch.object(engine, "_get_active_session", return_value="chaoxing-chrome-0"), \
             patch("chaoxing.browser.engine.subprocess.run", side_effect=fake_run), \
             patch("chaoxing.browser.engine.time.sleep"):
            out = pw("snapshot")
        assert out == "ok"
        assert len(calls) == 2


class TestRebuildWaitsForReady:
    """_rebuild_session polls until the fresh session answers a probe."""

    def test_ready_probe_success_path(self):
        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"), \
             patch("chaoxing.browser.engine.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="### Result\n1", stderr="")):
            assert engine._wait_session_ready("pw.cmd", "s-x") is True

    def test_ready_probe_error_stdout_not_ready(self):
        with patch("chaoxing.config.cfg", return_value="playwright-cli.cmd"), \
             patch("chaoxing.browser.engine.subprocess.run",
                   return_value=MagicMock(returncode=0, stdout="### Error\nx", stderr="")), \
             patch("chaoxing.browser.engine.time.time",
                   side_effect=[0, 0, 30]), \
             patch("chaoxing.browser.engine.time.sleep"):
            assert engine._wait_session_ready("pw.cmd", "s-x") is False
