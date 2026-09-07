"""
Shared pytest fixtures for the Chaoxing test suite.

Provides:
    - temp_workspace: Isolated workspace with minimal config.
    - mock_config: Valid test configuration.
    - mock_pw: Mock browser engine (no real playwright-cli calls).
    - real_browser_session: Real browser session (for E2E, skipped in CI).
"""

import json
import sys
import os
from pathlib import Path

import pytest

# Ensure the project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def temp_workspace(tmp_path):
    """Isolated workspace with minimal config for testing."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    scripts_dir = workspace / "scripts"
    scripts_dir.mkdir()
    # Runtime artifacts live in <tmp_path>/data (DATA_ROOT = WORKSPACE.parent/data)
    data_root = workspace.parent / "data"
    for sub in ("output", "temp", "logs", "screenshots", "chrome-profiles",
                "passwords", "documents"):
        (data_root / sub).mkdir(parents=True, exist_ok=True)

    # Create minimal config
    config = {
        "session": "chaoxing-chrome-test",
        "playwright_cli": "playwright-cli.cmd",
        "ai": {
            "provider": "doubao-api",
            "doubao": {
                "model": "test-model",
                "base_url": "https://test.api.example.com/v3",
                "timeout": 30,
                "max_retries": 1,
                "retry_base_delay": 1,
            },
        },
        "courses": [],
        "timeouts": {
            "page_load": 10,
            "snapshot": 5,
            "click_action": 3,
            "video_watch": 10,
            "quiz_answer": 30,
            "section_complete": 5,
        },
        "retry": {
            "quiz_max_retries": 3,
            "quiz_target_score": 100,
            "section_max_retries": 2,
        },
    }
    config_path = workspace / "chaoxing_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    # Set environment
    old_workspace = os.environ.get("CHAOXING_WORKSPACE")
    os.environ["CHAOXING_WORKSPACE"] = str(workspace)

    yield workspace

    # Restore
    if old_workspace:
        os.environ["CHAOXING_WORKSPACE"] = old_workspace
    else:
        os.environ.pop("CHAOXING_WORKSPACE", None)


@pytest.fixture
def mock_config(temp_workspace):
    """Return a valid ConfigManager instance for testing."""
    from chaoxing.config import ConfigManager
    config_path = temp_workspace / "chaoxing_config.json"
    return ConfigManager(config_path=config_path)


@pytest.fixture
def real_browser_session(request):
    """Skip unless --run-e2e flag is passed.

    Usage:
        pytest --run-e2e tests/e2e/
    """
    if not request.config.getoption("--run-e2e", default=False):
        pytest.skip("E2E tests require --run-e2e flag and a real browser")


def pytest_addoption(parser):
    parser.addoption(
        "--run-e2e", action="store_true", default=False,
        help="Run E2E tests that require a real browser"
    )
