"""Tests for chaoxing.platform.auth — credential parsing and login helpers."""
from chaoxing.platform import auth as auth_module
from chaoxing.platform.auth import _parse_credential_block


class TestParseCredentialBlock:
    """Credential parsing from passwords/chaoxing.txt format."""

    def test_simple_format(self):
        block = """
        account:13200003918
        password:test123
        """
        result = _parse_credential_block(block)
        assert result is not None
        assert result["account"] == "13200003918"
        assert result["password"] == "test123"
        assert result["index"] == 0

    def test_indexed_format(self):
        block = """
        account[2]:13800138000
        password[2]:pwd456
        """
        result = _parse_credential_block(block)
        assert result is not None
        assert result["account"] == "13800138000"
        assert result["password"] == "pwd456"
        assert result["index"] == 2

    def test_with_website(self):
        block = """
        website:https://example.com/login
        account:test@example.com
        password:secret
        """
        result = _parse_credential_block(block)
        assert result is not None
        assert result["website"] == "https://example.com/login"
        assert result["account"] == "test@example.com"

    def test_default_website_when_missing(self):
        block = """
        account:13800138000
        password:pwd
        """
        result = _parse_credential_block(block)
        assert result is not None
        assert "passport2.chaoxing.com" in result["website"]

    def test_quoted_values_stripped(self):
        block = """
        account:"13800138000"
        password:"quoted_pwd"
        """
        result = _parse_credential_block(block)
        assert result is not None
        assert result["account"] == "13800138000"
        assert result["password"] == "quoted_pwd"
        assert '"' not in result["account"]

    def test_braced_values_stripped(self):
        block = """
        account:{13800138000}
        password:{braced_pwd}
        """
        result = _parse_credential_block(block)
        assert result is not None
        assert result["account"] == "13800138000"
        assert result["password"] == "braced_pwd"

    def test_empty_block_returns_none(self):
        result = _parse_credential_block("")
        assert result is None

    def test_missing_password_returns_none(self):
        block = "account:test"
        result = _parse_credential_block(block)
        assert result is None

    def test_extra_fields_ignored(self):
        block = """
        account:test
        password:test123
        extra_field:should_be_ignored
        """
        result = _parse_credential_block(block)
        assert result is not None
        assert result["account"] == "test"

    def test_chinese_labels(self):
        block = """
        账号:13800138000
        密码:mypassword
        网站:https://example.com
        """
        result = _parse_credential_block(block)
        assert result is not None
        assert result["account"] == "13800138000"
        assert result["password"] == "mypassword"
        assert result["website"] == "https://example.com"

    def test_indexed_website_format(self):
        block = """
        website[2]:https://example.com/login
        account[2]:13800138000
        password[2]:pwd456
        """
        result = _parse_credential_block(block)
        assert result is not None
        assert result["website"] == "https://example.com/login"
        assert result["index"] == 2

    def test_indexed_chinese_website_format(self):
        block = """
        网站[1]:https://example.com/zh
        account[1]:13800138000
        password[1]:pwd456
        """
        result = _parse_credential_block(block)
        assert result is not None
        assert result["website"] == "https://example.com/zh"
        assert result["index"] == 1


class TestReadAllChaoxingCredentials:
    """Multi-account file parsing — explicit and implicit index assignment."""

    def _read(self, tmp_path, monkeypatch, text: str):
        cred_file = tmp_path / "chaoxing.txt"
        cred_file.write_text(text, encoding="utf-8")
        monkeypatch.setattr(auth_module, "accounts_file_path", lambda: cred_file)
        monkeypatch.setattr(auth_module, "_ALL_CREDS_CACHE", None)
        return auth_module.read_all_chaoxing_credentials()

    def test_two_unindexed_blocks_get_sequential_indices(self, tmp_path, monkeypatch):
        creds = self._read(tmp_path, monkeypatch, """{
account:13800000000
password:p0
}
{
account:13900000000
password:p1
}
""")
        assert [c["index"] for c in creds] == [0, 1]

    def test_unindexed_block_after_explicit_index_gets_next_slot(self, tmp_path, monkeypatch):
        creds = self._read(tmp_path, monkeypatch, """{
account[2]:13800000002
password[2]:p2
}
{
account:13900000000
password:p1
}
""")
        assert [c["index"] for c in creds] == [2, 3]
