from chaoxing.platform import auth
import chaoxing.browser.js_runner as js_runner


def test_open_uses_blank_then_goto(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return type("Completed", (), {"returncode": 0})()

    class FakeSubprocess:
        @staticmethod
        def run(cmd, **kw):
            return fake_run(cmd, **kw)

    monkeypatch.setattr(auth, "is_chaoxing_browser_open", lambda: False)
    monkeypatch.setattr(auth, "_session_is_headed", lambda s: None)
    monkeypatch.setattr(auth, "cfg", lambda k, d=None: "playwright-cli.cmd")
    monkeypatch.setattr(auth, "_kill_orphaned_chrome", lambda i: 0)
    monkeypatch.setattr(auth, "read_all_chaoxing_credentials",
                        lambda: [{"index": 0, "account": "a", "password": "p",
                                  "website": "https://x/login?a=1&b=2"}])
    monkeypatch.setattr(auth, "subprocess", FakeSubprocess)
    monkeypatch.setattr(auth, "pw_goto", lambda url: calls.append(("goto", url)))
    monkeypatch.setattr(auth.time, "sleep", lambda s: None)
    monkeypatch.setattr(auth, "log", lambda *a, **k: None)
    monkeypatch.setattr(js_runner, "_run_js_file", lambda *a, **k: "ok")

    auth.ensure_chaoxing_browser(0)
    assert calls[0][-1] == "about:blank"
    assert ("goto", "https://x/login?a=1&b=2") in calls
