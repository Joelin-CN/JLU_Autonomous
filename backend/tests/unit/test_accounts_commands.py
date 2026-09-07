import sys

import pytest

from chaoxing import accounts


def _write(path, text):
    path.write_text(text, encoding="utf-8")


def _run(tmp_path, monkeypatch, argv, f):
    monkeypatch.setattr(accounts, "accounts_file_path", lambda: f)
    monkeypatch.setattr(accounts.auth, "invalidate_credentials_cache", lambda: None)
    monkeypatch.setattr(sys, "argv", argv)
    captured = []
    monkeypatch.setattr(accounts, "_write_json_line", lambda obj: captured.append(obj))
    return captured


def test_add_reuses_lowest_free_index(tmp_path, monkeypatch):
    f = tmp_path / "chaoxing.txt"
    _write(f, """{
account[0]: 13800000000
password[0]: p0
}
{
account[2]: 13800000002
password[2]: p2
}
""")
    captured = _run(tmp_path, monkeypatch, [
        "chaoxing.accounts", "add", "--account", "13800000001",
        "--password", "p1",
    ], f)
    accounts.main()
    content = f.read_text(encoding="utf-8")
    assert "account[1]" in content and "password[1]" in content
    assert captured[-1]["type"] == "ACCOUNTS_OK"
    assert captured[-1]["index"] == 1


def test_remove_does_not_renumber(tmp_path, monkeypatch):
    f = tmp_path / "chaoxing.txt"
    _write(f, """{
account[0]: 13800000000
password[0]: p0
}
{
account[1]: 13800000001
password[1]: p1
}
{
account[2]: 13800000002
password[2]: p2
}
""")
    captured = _run(tmp_path, monkeypatch, [
        "chaoxing.accounts", "remove", "--index", "1",
    ], f)
    accounts.main()
    content = f.read_text(encoding="utf-8")
    assert "account[0]" in content and "account[2]" in content
    assert "account[1]" not in content


def test_add_rejects_duplicate(tmp_path, monkeypatch):
    f = tmp_path / "chaoxing.txt"
    _write(f, "{\naccount[0]: 13800000000\npassword[0]: p0\n}\n")
    captured = _run(tmp_path, monkeypatch, [
        "chaoxing.accounts", "add", "--account", "13800000000",
        "--password", "p1",
    ], f)
    with pytest.raises(SystemExit):
        accounts.main()
    assert captured[-1]["type"] == "ERROR"
    assert "duplicate" in captured[-1]["error"].lower()


def test_add_with_website_roundtrip(tmp_path, monkeypatch):
    f = tmp_path / "chaoxing.txt"
    _write(f, "{\naccount[0]: 13800000000\npassword[0]: p0\n}\n")
    captured = _run(tmp_path, monkeypatch, [
        "chaoxing.accounts", "add", "--account", "13800000001",
        "--password", "p1", "--website", "https://example.com/login",
    ], f)
    accounts.main()
    content = f.read_text(encoding="utf-8")
    assert "website[1]: https://example.com/login" in content
    assert captured[-1]["type"] == "ACCOUNTS_OK"
    parsed = accounts._read_creds()
    assert parsed[1]["website"] == "https://example.com/login"
    assert parsed[1]["index"] == 1
