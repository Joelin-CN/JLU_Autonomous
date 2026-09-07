"""Tests for chaoxing.config module."""

import json
from pathlib import Path

import pytest

from chaoxing.config import (
    cfg, load_config, get_config, ConfigManager,
    TimeoutConfig, RetryConfig, AIConfig, CourseConfig,
)
from chaoxing.exceptions import ConfigError


class TestLegacyConfig:
    """Test backward-compatible load_config() and cfg() functions."""

    def test_cfg_ai_provider(self):
        """cfg('ai.provider') should return the configured provider."""
        provider = cfg("ai.provider")
        assert provider in ("doubao-api", "deepseek-api")

    def test_cfg_timeout_default(self):
        """cfg() should return default when key not found."""
        result = cfg("timeouts.nonexistent", 999)
        assert result == 999

    def test_cfg_nested_default(self):
        """cfg() should return None (or specified default) for missing nested keys."""
        result = cfg("nonexistent.nested.key", "fallback")
        assert result == "fallback"

    def test_load_config_returns_dict(self):
        """load_config() should return the raw config dict."""
        config = load_config()
        assert isinstance(config, dict)
        assert "courses" in config
        assert "ai" in config
        assert "timeouts" in config

    def test_cfg_retry_target(self):
        """cfg() should return nested retry config values."""
        target = cfg("retry.quiz_target_score", 100)
        assert isinstance(target, int)
        assert target >= 0


class TestConfigManager:
    """Test the new ConfigManager API."""

    def test_get_courses(self):
        """get_courses() should return a list of CourseConfig."""
        mgr = get_config()
        courses = mgr.get_courses()
        assert isinstance(courses, list)
        for course in courses:
            assert course.name
            assert course.courseid

    def test_ai_provider_property(self):
        """ai_provider property should match config file."""
        mgr = get_config()
        provider = mgr.ai_provider
        assert provider in ("doubao-api", "deepseek-api")

    def test_get_method(self):
        """get() should work like legacy cfg()."""
        mgr = get_config()
        provider = mgr.get("ai.provider")
        assert provider in ("doubao-api", "deepseek-api")

    def test_reload(self):
        """reload() should re-read config from disk."""
        mgr = get_config()
        old_provider = mgr.ai_provider
        mgr.reload()
        assert mgr.ai_provider == old_provider  # Should be same file

    def test_missing_config_file(self, tmp_path):
        """Should raise ConfigError for missing config file."""
        bad_path = tmp_path / "nonexistent.json"
        with pytest.raises(ConfigError):
            ConfigManager(config_path=bad_path)

    def test_get_course_by_name_exact(self):
        """get_course_by_name() with exact name should find the course."""
        mgr = get_config()
        courses = mgr.get_courses()
        if courses:
            course = mgr.get_course_by_name(courses[0].name)
            assert course is not None
            assert course.name == courses[0].name

    def test_get_course_by_name_substring(self):
        """get_course_by_name() with substring should find matching course."""
        mgr = get_config()
        courses = mgr.get_courses()
        if courses:
            # Use first 2 chars as substring (should match at least one)
            substr = courses[0].name[:2]
            course = mgr.get_course_by_name(substr)
            assert course is not None

    def test_get_course_by_name_nonexistent(self):
        """get_course_by_name() with nonexistent name should return None."""
        mgr = get_config()
        course = mgr.get_course_by_name("ZZZ_NONEXISTENT_COURSE_12345_ZZZ")
        assert course is None

    def test_timeout_config_defaults(self):
        """TimeoutConfig should have sensible defaults."""
        mgr = get_config()
        assert mgr.timeouts.page_load >= 10
        assert mgr.timeouts.snapshot >= 5
        assert mgr.timeouts.quiz_answer >= 30

    def test_retry_config_defaults(self):
        """RetryConfig should have sensible defaults."""
        mgr = get_config()
        assert mgr.retry.quiz_target_score >= 0
        assert mgr.retry.quiz_max_retries >= 1

    def test_session_default(self):
        """Session should default to chaoxing-chrome."""
        mgr = get_config()
        assert "chaoxing-chrome" in mgr.session


class TestDataclassModels:
    """Test config dataclass from_dict() constructors."""

    def test_timeout_config_from_empty_dict(self):
        tc = TimeoutConfig.from_dict({})
        assert tc.page_load == 30
        assert tc.snapshot == 15
        assert tc.quiz_answer == 120

    def test_timeout_config_from_partial_dict(self):
        tc = TimeoutConfig.from_dict({"page_load": 60})
        assert tc.page_load == 60
        assert tc.snapshot == 15  # default preserved

    def test_timeout_config_from_full_dict(self):
        d = {
            "page_load": 45, "snapshot": 20, "click_action": 15,
            "video_watch": 90, "quiz_answer": 180, "section_complete": 30,
        }
        tc = TimeoutConfig.from_dict(d)
        assert tc.page_load == 45
        assert tc.video_watch == 90
        assert tc.section_complete == 30

    def test_retry_config_from_empty_dict(self):
        rc = RetryConfig.from_dict({})
        assert rc.quiz_max_retries == 10
        assert rc.quiz_target_score == 100

    def test_retry_config_from_partial_dict(self):
        rc = RetryConfig.from_dict({"quiz_target_score": 85})
        assert rc.quiz_target_score == 85
        assert rc.quiz_max_retries == 10  # default preserved

    def test_ai_config_from_empty_dict(self):
        ac = AIConfig.from_dict({})
        assert ac.provider == "doubao-api"
        assert "volces.com" in ac.doubao_base_url

    def test_ai_config_from_partial_dict(self):
        ac = AIConfig.from_dict({"provider": "doubao-api", "doubao": {"model": "custom-model"}})
        assert ac.provider == "doubao-api"
        assert ac.doubao_model == "custom-model"

    def test_ai_config_doubao_subsection(self):
        ac = AIConfig.from_dict({
            "provider": "doubao-api",
            "doubao": {"model": "ep-20250101-test", "timeout": 300},
        })
        assert ac.doubao_model == "ep-20250101-test"
        assert ac.doubao_timeout == 300
        assert ac.doubao_max_retries == 3  # default preserved

    def test_course_config_from_minimal_dict(self):
        cc = CourseConfig.from_dict({
            "name": "测试课程",
            "courseid": "12345",
            "clazzid": "67890",
        })
        assert cc.name == "测试课程"
        assert cc.courseid == "12345"
        assert cc.clazzid == "67890"
        assert cc.cpi == "415409200"  # default
        assert cc.priority == 99  # default

    def test_course_config_from_full_dict(self):
        cc = CourseConfig.from_dict({
            "name": "完整课程",
            "courseid": 98765,
            "clazzid": 43210,
            "cpi": "111111",
            "priority": 1,
            "current_progress": 5,
            "total_tasks": 20,
        })
        assert cc.courseid == "98765"  # converted to string
        assert cc.clazzid == "43210"
        assert cc.cpi == "111111"
        assert cc.priority == 1
        assert cc.current_progress == 5
        assert cc.total_tasks == 20
