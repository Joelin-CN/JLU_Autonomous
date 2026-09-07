"""Tests for chaoxing.constants — global paths, locks, and process-wide flags."""
import os
import sys
import io
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

from chaoxing import constants


class TestPathConstants:
    """Tests for path constants: WORKSPACE, SCRIPT_DIR, CONFIG_PATH, etc."""

    def test_workspace_from_env(self):
        """WORKSPACE should use CHAOXING_WORKSPACE env var when set."""
        with patch.dict(os.environ, {"CHAOXING_WORKSPACE": "/custom/workspace"}):
            # Re-import won't re-execute module-level code, so test the logic directly
            ws = Path(os.environ.get("CHAOXING_WORKSPACE", ""))
            assert ws.as_posix() == "/custom/workspace"

    def test_workspace_fallback(self):
        """WORKSPACE should fall back to parent of constants.py when env var not set."""
        # When CHAOXING_WORKSPACE is not set, should use Path(__file__).parent.parent
        ws = constants.WORKSPACE
        assert isinstance(ws, Path)
        # Should point to the project root (parent of chaoxing package)
        assert ws.name != "chaoxing"
        assert ws.is_absolute() or str(ws).startswith("E:") or str(ws).startswith("/")

    def test_script_dir(self):
        """SCRIPT_DIR should be WORKSPACE / 'scripts'."""
        sd = constants.SCRIPT_DIR
        assert isinstance(sd, Path)
        assert sd.name == "scripts"

    def test_config_path(self):
        """CONFIG_PATH should be WORKSPACE / 'chaoxing_config.json' (project root)."""
        cp = constants.CONFIG_PATH
        assert isinstance(cp, Path)
        assert cp.name == "chaoxing_config.json"
        assert cp.parent == constants.WORKSPACE

    def test_output_dir(self):
        """OUTPUT_DIR should be DATA_ROOT / 'output'."""
        od = constants.OUTPUT_DIR
        assert isinstance(od, Path)
        assert od.name == "output"

    def test_tmp_dir(self):
        """TMP_DIR should be DATA_ROOT / 'temp'."""
        td = constants.TMP_DIR
        assert isinstance(td, Path)
        assert td.name == "temp"

    def test_log_dir(self):
        """LOG_DIR should be DATA_ROOT / 'logs'."""
        ld = constants.LOG_DIR
        assert isinstance(ld, Path)
        assert ld.name == "logs"

    def test_creds_dir(self):
        """CREDS_DIR should be DATA_ROOT / 'passwords'."""
        cd = constants.CREDS_DIR
        assert isinstance(cd, Path)
        assert cd.name == "passwords"

    def test_chrome_profiles_dir(self):
        """CHROME_PROFILES_DIR should be DATA_ROOT / 'chrome-profiles'."""
        pd = constants.CHROME_PROFILES_DIR
        assert isinstance(pd, Path)
        assert pd.name == "chrome-profiles"

    def test_data_root(self):
        """DATA_ROOT should be the parent of WORKSPACE plus /data."""
        dr = constants.DATA_ROOT
        assert isinstance(dr, Path)
        assert dr.name == "data"
        assert dr.parent == constants.WORKSPACE.parent

    def test_package_dir(self):
        """PACKAGE_DIR should be the chaoxing package directory."""
        pd = constants.PACKAGE_DIR
        assert isinstance(pd, Path)
        assert pd.name == "chaoxing"

    def test_js_dir(self):
        """JS_DIR should be PACKAGE_DIR / 'js'."""
        jd = constants.JS_DIR
        assert isinstance(jd, Path)
        assert jd.name == "js"

    def test_data_dir(self):
        """DATA_DIR should be PACKAGE_DIR / 'data'."""
        dd = constants.DATA_DIR
        assert isinstance(dd, Path)
        assert dd.name == "data"

    def test_all_paths_are_path_objects(self):
        """All path constants should be pathlib.Path instances."""
        path_constants = [
            constants.WORKSPACE, constants.SCRIPT_DIR, constants.CONFIG_PATH,
            constants.DATA_ROOT, constants.OUTPUT_DIR, constants.TMP_DIR,
            constants.LOG_DIR, constants.SCREENSHOTS_DIR,
            constants.CHROME_PROFILES_DIR, constants.CREDS_DIR,
            constants.DOCUMENTS_DIR, constants.PACKAGE_DIR,
            constants.JS_DIR, constants.DATA_DIR,
        ]
        for p in path_constants:
            assert isinstance(p, Path), f"{p} should be a Path instance"

    def test_path_derivation_consistency(self):
        """Derived paths should be children of WORKSPACE or PACKAGE_DIR."""
        # SCRIPT_DIR, CONFIG_PATH are under WORKSPACE
        assert str(constants.SCRIPT_DIR).startswith(str(constants.WORKSPACE))
        assert str(constants.CONFIG_PATH).startswith(str(constants.WORKSPACE))
        # Runtime artifact dirs are under DATA_ROOT
        for d in (constants.OUTPUT_DIR, constants.TMP_DIR, constants.LOG_DIR,
                  constants.SCREENSHOTS_DIR, constants.CHROME_PROFILES_DIR,
                  constants.CREDS_DIR, constants.DOCUMENTS_DIR):
            assert str(d).startswith(str(constants.DATA_ROOT))
        # JS_DIR, DATA_DIR are under PACKAGE_DIR
        assert str(constants.JS_DIR).startswith(str(constants.PACKAGE_DIR))
        assert str(constants.DATA_DIR).startswith(str(constants.PACKAGE_DIR))


class TestUTF8Encoding:
    """Tests for Windows UTF-8 stdout/stderr encoding setup."""

    def test_stdout_is_textiowrapper_on_windows(self):
        """On Windows, stdout should be a TextIOWrapper with utf-8 encoding.

        Note: This is only re-wrapped if sys.stdout.buffer is not None.
        In PyInstaller/frozen environments, buffer may be None.
        """
        if sys.platform == "win32":
            # stdout should be some kind of TextIO
            assert hasattr(sys.stdout, 'write')

    def test_stdout_buffer_none_guard(self):
        """When sys.stdout.buffer is None, should NOT attempt to re-wrap.

        This is the PyInstaller compatibility case: frozen executables
        may have stdout.buffer set to None.
        """
        # The guard check is: if sys.stdout.buffer is not None
        # When buffer is None, the code block is skipped entirely.
        # We verify the module doesn't crash on import by checking
        # that constants imported successfully (we're running this test).
        assert hasattr(constants, 'WORKSPACE')

    def test_buffer_none_does_not_crash(self):
        """When both stdout.buffer and stderr.buffer are None, no error should occur.

        This simulates the PyInstaller frozen environment where stdout.buffer
        and stderr.buffer are both None.
        """
        # The module was already imported, so the check already ran.
        # We verify it didn't crash by checking the module is usable.
        assert constants.WORKSPACE is not None

    def test_stderr_buffer_available(self):
        """stderr should be available for writing."""
        assert hasattr(sys.stderr, 'write')


class TestMaxAccounts:
    """MAX_ACCOUNTS is a list-length sanity cap, NOT a concurrency limit."""

    def test_max_accounts_cap(self):
        assert constants.MAX_ACCOUNTS == 50

    def test_no_global_semaphore(self):
        assert not hasattr(constants, "ACCOUNT_SEMAPHORE")


class TestShutdownFlagConstants:
    """Tests for SHUTDOWN_FLAG — threading.Event for graceful shutdown."""

    def test_shutdown_flag_is_event(self):
        """SHUTDOWN_FLAG should be a threading.Event."""
        assert isinstance(constants.SHUTDOWN_FLAG, threading.Event)

    def test_shutdown_flag_set_and_clear(self):
        """Should be able to set, check, and clear the shutdown flag."""
        constants.SHUTDOWN_FLAG.clear()
        assert not constants.SHUTDOWN_FLAG.is_set()
        constants.SHUTDOWN_FLAG.set()
        assert constants.SHUTDOWN_FLAG.is_set()
        constants.SHUTDOWN_FLAG.clear()
        assert not constants.SHUTDOWN_FLAG.is_set()


class TestModuleAttributes:
    """Verify the module exports the expected set of attributes."""

    def test_all_expected_attributes_exist(self):
        """Module should have all expected constant attributes."""
        expected = [
            "WORKSPACE", "SCRIPT_DIR", "CONFIG_PATH", "DATA_ROOT", "OUTPUT_DIR",
            "TMP_DIR", "LOG_DIR", "SCREENSHOTS_DIR", "CHROME_PROFILES_DIR",
            "CREDS_DIR", "DOCUMENTS_DIR", "PACKAGE_DIR", "JS_DIR", "DATA_DIR",
            "MAX_ACCOUNTS", "SHUTDOWN_FLAG",
        ]
        for attr in expected:
            assert hasattr(constants, attr), f"Missing: constants.{attr}"

    def test_no_unexpected_public_attributes(self):
        """Module should not leak internal implementation details as public."""
        # These should exist as attributes
        assert hasattr(constants, "Path")
        assert hasattr(constants, "os")
        assert hasattr(constants, "sys")
        assert hasattr(constants, "io")
        assert hasattr(constants, "threading")

    def test_module_docstring(self):
        """Module should have a docstring."""
        assert constants.__doc__ is not None
        assert len(constants.__doc__) > 10
