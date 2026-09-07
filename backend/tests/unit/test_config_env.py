import json

from chaoxing.config import ConfigManager


def _write_config(tmp_path):
    path = tmp_path / "chaoxing_config.json"
    path.write_text(json.dumps({
        "session": "chaoxing-chrome",
        "timeouts": {"page_load": 30, "snapshot": 15, "click_action": 10,
                     "video_watch": 60, "quiz_answer": 120},
        "retry": {"quiz_max_retries": 10, "quiz_target_score": 100},
        "courses": [],
    }, ensure_ascii=False), encoding="utf-8")
    return path


def test_env_overrides_reach_legacy_cfg_and_typed(monkeypatch, tmp_path):
    monkeypatch.setenv("CHAOXING_TIMEOUT_PAGE_LOAD", "45")
    monkeypatch.setenv("CHAOXING_TIMEOUT_QUIZ_ANSWER", "200")
    monkeypatch.setenv("CHAOXING_RETRY_QUIZ_MAX", "7")
    monkeypatch.setenv("CHAOXING_RETRY_TARGET_SCORE", "90")

    mgr = ConfigManager(config_path=_write_config(tmp_path))

    assert mgr.get("timeouts.page_load") == 45
    assert mgr.get("timeouts.quiz_answer") == 200
    assert mgr.get("timeouts.video_watch") == 60  # untouched
    assert mgr.get("retry.quiz_max_retries") == 7
    assert mgr.get("retry.quiz_target_score") == 90
    assert mgr.timeouts.page_load == 45
    assert mgr.retry.quiz_max_retries == 7
