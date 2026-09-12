"""
Configuration management with dataclass-based validation.

Backward-compatible with the original chaoxing_config.json format.
Provides both the legacy dict-style access (load_config / cfg) and typed
dataclass access (ConfigManager.get_courses() etc.).

Usage:
    from core.config import load_config, cfg, get_config

    # Legacy API (compatible with original utils.py)
    provider = cfg("ai.provider")
    timeout = cfg("timeouts.quiz_answer", 120)

    # New typed API
    config = get_config()
    config.reload()
    courses = config.get_courses()
"""

import json
import os
import sys
import warnings
from pathlib import Path
from dataclasses import dataclass, field, fields
from typing import Any, Optional

from core.constants import CONFIG_PATH
from core.exceptions import ConfigError


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        warnings.warn(f"Ignoring non-integer {name}={raw!r}", UserWarning, stacklevel=3)
        return default


def _warn_unknown_keys(d: dict, known_keys: set, class_name: str):
    """Emit warnings for unrecognized keys in config dicts (catches typos)."""
    unknown = set(d.keys()) - known_keys
    for key in sorted(unknown):
        warnings.warn(
            f"Unrecognized config key '{key}' in {class_name} — typo? "
            f"Expected one of: {sorted(known_keys)}",
            UserWarning, stacklevel=3
        )


# ── Typed Config Models ─────────────────────────────────────────

@dataclass
class TimeoutConfig:
    """Per-operation timeout values (seconds)."""
    page_load: int = 30
    snapshot: int = 15
    click_action: int = 10
    video_watch: int = 60
    quiz_answer: int = 120
    section_complete: int = 15

    @classmethod
    def from_dict(cls, d: dict) -> "TimeoutConfig":
        _warn_unknown_keys(d, {'page_load', 'snapshot', 'click_action',
                               'video_watch', 'quiz_answer', 'section_complete'},
                           'TimeoutConfig')
        return cls(
            page_load=_env_int("CHAOXING_TIMEOUT_PAGE_LOAD", d.get("page_load", 30)),
            snapshot=_env_int("CHAOXING_TIMEOUT_SNAPSHOT", d.get("snapshot", 15)),
            click_action=_env_int("CHAOXING_TIMEOUT_CLICK_ACTION", d.get("click_action", 10)),
            video_watch=_env_int("CHAOXING_TIMEOUT_VIDEO_WATCH", d.get("video_watch", 60)),
            quiz_answer=_env_int("CHAOXING_TIMEOUT_QUIZ_ANSWER", d.get("quiz_answer", 120)),
            section_complete=_env_int("CHAOXING_TIMEOUT_SECTION_COMPLETE",
                                      d.get("section_complete", 15)),
        )


@dataclass
class RetryConfig:
    """Retry parameters for quiz solving."""
    quiz_max_retries: int = 10
    quiz_target_score: int = 100
    section_max_retries: int = 3

    @classmethod
    def from_dict(cls, d: dict) -> "RetryConfig":
        _warn_unknown_keys(d, {'quiz_max_retries', 'quiz_target_score', 'section_max_retries'},
                           'RetryConfig')
        return cls(
            quiz_max_retries=_env_int("CHAOXING_RETRY_QUIZ_MAX",
                                      d.get("quiz_max_retries", 10)),
            quiz_target_score=_env_int("CHAOXING_RETRY_TARGET_SCORE",
                                       d.get("quiz_target_score", 100)),
            section_max_retries=d.get("section_max_retries", 3),
        )


@dataclass
class AIConfig:
    """AI backend configuration."""
    provider: str = "doubao-api"
    doubao_model: str = ""
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_timeout: int = 180
    doubao_max_retries: int = 3
    doubao_retry_base_delay: int = 2
    deepseek_model: str = "deepseek-v4-flash-vision-exp"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_timeout: int = 180
    deepseek_max_retries: int = 3
    deepseek_retry_base_delay: int = 2

    @classmethod
    def from_dict(cls, d: dict) -> "AIConfig":
        _warn_unknown_keys(d, {'provider', 'doubao', 'deepseek', 'note'},
                           'AIConfig')
        doubao = d.get("doubao", {})
        _warn_unknown_keys(doubao, {'model', 'base_url', 'timeout', 'max_retries', 'retry_base_delay'},
                           'AIConfig.doubao')
        deepseek = d.get("deepseek", {})
        _warn_unknown_keys(deepseek, {'model', 'base_url', 'timeout', 'max_retries', 'retry_base_delay'},
                           'AIConfig.deepseek')
        return cls(
            provider=d.get("provider", "doubao-api"),
            doubao_model=doubao.get("model", ""),
            doubao_base_url=doubao.get("base_url", "https://ark.cn-beijing.volces.com/api/v3"),
            doubao_timeout=doubao.get("timeout", 180),
            doubao_max_retries=doubao.get("max_retries", 3),
            doubao_retry_base_delay=doubao.get("retry_base_delay", 2),
            deepseek_model=deepseek.get("model", "deepseek-v4-flash-vision-exp"),
            deepseek_base_url=deepseek.get("base_url", "https://api.deepseek.com"),
            deepseek_timeout=deepseek.get("timeout", 180),
            deepseek_max_retries=deepseek.get("max_retries", 3),
            deepseek_retry_base_delay=deepseek.get("retry_base_delay", 2),
        )


@dataclass
class CourseConfig:
    """Single course configuration."""
    name: str
    courseid: str
    clazzid: str
    cpi: str = "415409200"
    priority: int = 99
    current_progress: int = 0
    total_tasks: int = 0
    # Extended fields for course structure (set post-discovery or in config)
    remaining_quiz_sections: Optional[list] = None
    remaining_content_sections: Optional[list] = None
    chapters: Optional[list] = None

    @classmethod
    def from_dict(cls, d: dict) -> "CourseConfig":
        _warn_unknown_keys(d, {'name', 'courseid', 'clazzid', 'cpi', 'priority',
                               'current_progress', 'total_tasks',
                               'remaining_quiz_sections', 'remaining_content_sections',
                               'chapters'},
                           'CourseConfig')
        return cls(
            name=d.get("name", ""),
            courseid=str(d.get("courseid", "")),
            clazzid=str(d.get("clazzid", "")),
            cpi=str(d.get("cpi", "415409200")),
            priority=d.get("priority", 99),
            current_progress=d.get("current_progress", 0),
            total_tasks=d.get("total_tasks", 0),
            remaining_quiz_sections=d.get("remaining_quiz_sections"),
            remaining_content_sections=d.get("remaining_content_sections"),
            chapters=d.get("chapters"),
        )


# ── Config Manager ──────────────────────────────────────────────

class ConfigManager:
    """Centralized configuration with validation and reload support.

    Reads from chaoxing_config.json at the project root (CONFIG_PATH).
    Provides both typed dataclass access and legacy dict-style access.
    """

    def __init__(self, config_path: Path = None):
        self._path = config_path or CONFIG_PATH
        self._raw: dict = {}
        self.timeouts: TimeoutConfig = TimeoutConfig()
        self.retry: RetryConfig = RetryConfig()
        self.ai_config: AIConfig = AIConfig()
        self._courses: list[CourseConfig] = []
        self.session: str = "chaoxing-chrome"
        self.playwright_cli: str = "playwright-cli.cmd"
        self.chrome_args: list[str] = ["--disable-gpu", "--disable-software-rasterizer"]
        self.max_concurrent: int = 10
        self._load()

    def _load(self):
        """Load and parse the JSON config file."""
        if not self._path.exists():
            raise ConfigError(f"Config file not found: {self._path}")
        with open(self._path, "r", encoding="utf-8") as f:
            try:
                self._raw = json.load(f)
            except json.JSONDecodeError as e:
                raise ConfigError(f"Invalid JSON in config file {self._path}: {e}") from e

        self.session = self._raw.get("session", "chaoxing-chrome")
        self.playwright_cli = self._raw.get("playwright_cli", "playwright-cli.cmd")
        self.chrome_args = self._raw.get("chrome_args", ["--disable-gpu", "--disable-software-rasterizer"])
        self.max_concurrent = self._raw.get("max_concurrent", 10)

        # Environment overrides (Electron settings → PythonBridge env). Merge
        # into the legacy _raw dict so BOTH cfg("timeouts.*") and the typed
        # TimeoutConfig/RetryConfig dataclasses observe the same values.
        _timeout_env = {
            "page_load": "CHAOXING_TIMEOUT_PAGE_LOAD",
            "snapshot": "CHAOXING_TIMEOUT_SNAPSHOT",
            "click_action": "CHAOXING_TIMEOUT_CLICK_ACTION",
            "video_watch": "CHAOXING_TIMEOUT_VIDEO_WATCH",
            "quiz_answer": "CHAOXING_TIMEOUT_QUIZ_ANSWER",
            "section_complete": "CHAOXING_TIMEOUT_SECTION_COMPLETE",
        }
        timeouts_raw = dict(self._raw.get("timeouts", {}))
        for key, env_name in _timeout_env.items():
            if os.environ.get(env_name):
                timeouts_raw[key] = _env_int(env_name, timeouts_raw.get(key, 0))
        if timeouts_raw:
            self._raw["timeouts"] = timeouts_raw

        retry_raw = dict(self._raw.get("retry", {}))
        if os.environ.get("CHAOXING_RETRY_QUIZ_MAX"):
            retry_raw["quiz_max_retries"] = _env_int(
                "CHAOXING_RETRY_QUIZ_MAX", retry_raw.get("quiz_max_retries", 10))
        if os.environ.get("CHAOXING_RETRY_TARGET_SCORE"):
            retry_raw["quiz_target_score"] = _env_int(
                "CHAOXING_RETRY_TARGET_SCORE", retry_raw.get("quiz_target_score", 100))
        if retry_raw:
            self._raw["retry"] = retry_raw

        self.timeouts = TimeoutConfig.from_dict(self._raw.get("timeouts", {}))
        self.retry = RetryConfig.from_dict(self._raw.get("retry", {}))
        self.ai_config = AIConfig.from_dict(self._raw.get("ai", {}))

        courses_raw = self._raw.get("courses", [])
        self._courses = [CourseConfig.from_dict(c) for c in courses_raw]

    def reload(self):
        """Reload configuration from disk."""
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style access with dot-notation keys (backward compatible with cfg())."""
        parts = key.split(".")
        c = self._raw
        for part in parts:
            if isinstance(c, dict):
                c = c.get(part, default)
            else:
                return default
        return c

    def get_courses(self) -> list[CourseConfig]:
        """Return all configured courses."""
        return list(self._courses)

    def get_course_by_name(self, name: str) -> Optional[CourseConfig]:
        """Find a course by exact or substring name match."""
        for course in self._courses:
            if course.name == name or name in course.name:
                return course
        return None

    def add_chrome_args(self, flags: list[str]) -> None:
        """Merge extra Chromium launch flags into chrome_args at runtime.

        Used by api.py to forward the frontend's --chromium-flags (memory
        mitigations like --renderer-process-limit / --disable-dev-shm-usage)
        to the actual Chrome launch in platform.auth. Duplicates are skipped
        so repeated calls are idempotent. Both the typed attribute and the
        legacy _raw dict (read by cfg()) are updated so all readers agree.
        """
        if not flags:
            return
        existing = list(self.chrome_args)
        for f in flags:
            if f and f not in existing:
                existing.append(f)
        self.chrome_args = existing
        self._raw["chrome_args"] = existing

    @property
    def ai_provider(self) -> str:
        return self.ai_config.provider


# ── Legacy-Compatible API ───────────────────────────────────────

_config: Optional[ConfigManager] = None
_legacy_config: Optional[dict] = None  # Cached dict for legacy cfg()

def get_config() -> ConfigManager:
    """Get or lazily create the ConfigManager singleton."""
    global _config
    if _config is None:
        _config = ConfigManager()
    return _config


def load_config():
    """Legacy API: Return the raw config dict.

    Maintains backward compatibility with original utils.py interface.
    """
    global _legacy_config
    if _legacy_config is None:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _legacy_config = json.load(f)
    return _legacy_config


def cfg(key: str, default=None):
    """Legacy API: Access config values with dot-notation keys.

    Now routes through ConfigManager.get() to ensure reload() consistency.
    Maintains backward compatibility with original utils.py interface.

    Examples:
        cfg("ai.provider")           -> "doubao-api"
        cfg("timeouts.quiz_answer")  -> 120
    """
    return get_config().get(key, default)
