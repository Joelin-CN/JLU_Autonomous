import json

import pytest

from chaoxing import ai_config


def test_test_ok(monkeypatch, capsys):
    class FakeModels:
        def list(self):
            return type("L", (), {"data": [1, 2, 3]})()

    class FakeClient:
        def __init__(self, **kw):
            pass
        models = FakeModels()

    monkeypatch.setattr(ai_config, "_load_credentials",
                        lambda provider="doubao-api": {"api_key": "ark-x", "model": "ep-1"})
    monkeypatch.setattr(ai_config, "cfg", lambda *a, **k: "doubao-api")
    monkeypatch.setattr(ai_config, "OpenAI", FakeClient)
    ai_config.run_test()
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(line) == {"type": "AI_TEST", "ok": True, "models": 3}


def test_test_auth_failure(monkeypatch, capsys):
    class FakeModels:
        def list(self):
            raise Exception("401 Unauthorized")

    class FakeClient:
        def __init__(self, **kw):
            pass
        models = FakeModels()

    monkeypatch.setattr(ai_config, "_load_credentials",
                        lambda provider="doubao-api": {"api_key": "ark-x", "model": "ep-1"})
    monkeypatch.setattr(ai_config, "cfg", lambda *a, **k: "doubao-api")
    monkeypatch.setattr(ai_config, "OpenAI", FakeClient)
    with pytest.raises(SystemExit) as e:
        ai_config.run_test()
    assert e.value.code == 1
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert "401" in payload["reason"]
