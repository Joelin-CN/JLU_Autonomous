"""Tests for chaoxing.ai.billing and the chaoxing.balance CLI.

The volcengine SDK is NOT installed under the system Python that runs these
tests, so every SDK interaction is mocked:
    - credential parsing uses a tmp file patched onto billing.CREDS_FILE
    - query_balance() injects fake volcenginesdkcore/volcenginesdkbilling into
      sys.modules so the lazy `import` inside the function resolves to mocks
    - the SDK-missing path injects a sentinel that raises ModuleNotFoundError
"""
import io
import json
import sys
from unittest.mock import patch, MagicMock

import pytest

from chaoxing import balance as balance_cli
from chaoxing.ai import billing
from chaoxing.exceptions import ConfigError, AIBackendError


# ══════════════════════════════════════════════════════════════════
#  Credential parsing
# ══════════════════════════════════════════════════════════════════

class TestLoadBillingCredentials:

    def _write_creds(self, tmp_path, text):
        f = tmp_path / "volc_billing.txt"
        f.write_text(text, encoding="utf-8")
        return f

    def test_parses_export_quoted_form(self, tmp_path):
        f = self._write_creds(tmp_path,
            'export VOLC_ACCESS_KEY="AKabc123"\n'
            'export VOLC_SECRET_KEY="SKdef456"\n'
            'region="cn-beijing"\n')
        with patch.object(billing, "CREDS_FILE", f):
            creds = billing._load_billing_credentials()
        assert creds == {
            "access_key": "AKabc123",
            "secret_key": "SKdef456",
            "region": "cn-beijing",
        }

    def test_parses_bare_env_form(self, tmp_path):
        f = self._write_creds(tmp_path,
            'VOLC_ACCESS_KEY=AKbare\n'
            'VOLC_SECRET_KEY=SKbare\n')
        with patch.object(billing, "CREDS_FILE", f):
            creds = billing._load_billing_credentials()
        assert creds["access_key"] == "AKbare"
        assert creds["secret_key"] == "SKbare"

    def test_parses_gbk_encoded_file(self, tmp_path):
        # Chinese Windows editors commonly save plain text as ANSI/GBK; the
        # loader must tolerate that, not just UTF-8.
        f = tmp_path / "volc_billing.txt"
        f.write_text(
            'VOLC_ACCESS_KEY="AKgbk123"\nVOLC_SECRET_KEY="SKgbk456"\n',
            encoding="gbk",
        )
        with patch.object(billing, "CREDS_FILE", f):
            creds = billing._load_billing_credentials()
        assert creds["access_key"] == "AKgbk123"
        assert creds["secret_key"] == "SKgbk456"

    def test_region_defaults_when_absent(self, tmp_path):
        f = self._write_creds(tmp_path,
            'VOLC_ACCESS_KEY=AK\nVOLC_SECRET_KEY=SK\n')
        with patch.object(billing, "CREDS_FILE", f):
            creds = billing._load_billing_credentials()
        assert creds["region"] == billing.DEFAULT_REGION == "cn-north-1"

    def test_missing_file_raises_config_error(self, tmp_path):
        missing = tmp_path / "does_not_exist.txt"
        with patch.object(billing, "CREDS_FILE", missing):
            with pytest.raises(ConfigError, match="not found"):
                billing._load_billing_credentials()

    def test_missing_access_key_raises_config_error(self, tmp_path):
        f = self._write_creds(tmp_path, 'VOLC_SECRET_KEY=SKonly\n')
        with patch.object(billing, "CREDS_FILE", f):
            with pytest.raises(ConfigError, match="VOLC_ACCESS_KEY"):
                billing._load_billing_credentials()

    def test_missing_secret_key_raises_config_error(self, tmp_path):
        f = self._write_creds(tmp_path, 'VOLC_ACCESS_KEY=AKonly\n')
        with patch.object(billing, "CREDS_FILE", f):
            with pytest.raises(ConfigError, match="VOLC_SECRET_KEY"):
                billing._load_billing_credentials()


# ══════════════════════════════════════════════════════════════════
#  query_balance — SDK mocked via sys.modules
# ══════════════════════════════════════════════════════════════════

def _make_fake_sdk(resp):
    """Build fake volcenginesdkcore / volcenginesdkbilling modules.

    Returns (core_mod, billing_mod, api_instance) so tests can assert on calls.
    """
    core_mod = MagicMock(name="volcenginesdkcore")
    # Configuration() returns a fresh settable object; set_default is a classmethod.
    core_mod.Configuration.return_value = MagicMock(name="cfg")

    billing_mod = MagicMock(name="volcenginesdkbilling")
    api_instance = MagicMock(name="BILLINGApi-instance")
    api_instance.query_balance_acct.return_value = resp
    billing_mod.BILLINGApi.return_value = api_instance
    billing_mod.QueryBalanceAcctRequest.return_value = MagicMock(name="request")

    return core_mod, billing_mod, api_instance


def _fake_response():
    resp = MagicMock(name="QueryBalanceAcctResponse")
    resp.account_id = 2100123456
    resp.available_balance = "100.50"
    resp.cash_balance = "80.25"
    resp.credit_limit = "0.00"
    resp.arrears_balance = "0.00"
    resp.freeze_amount = "5.00"
    return resp


class TestQueryBalance:

    def test_normalizes_response_to_camelcase(self):
        core_mod, billing_mod, api_instance = _make_fake_sdk(_fake_response())
        creds = {"access_key": "AK", "secret_key": "SK", "region": "cn-north-1"}
        with patch.object(billing, "_load_billing_credentials", return_value=creds), \
             patch.dict(sys.modules, {
                 "volcenginesdkcore": core_mod,
                 "volcenginesdkbilling": billing_mod,
             }):
            result = billing.query_balance()

        assert result == {
            "accountId": 2100123456,
            "availableBalance": "100.50",
            "cashBalance": "80.25",
            "creditLimit": "0.00",
            "arrearsBalance": "0.00",
            "freezeAmount": "5.00",
            "currency": "CNY",
        }

    def test_configures_ak_sk_region(self):
        core_mod, billing_mod, api_instance = _make_fake_sdk(_fake_response())
        cfg = core_mod.Configuration.return_value
        creds = {"access_key": "AKxx", "secret_key": "SKyy", "region": "cn-beijing"}
        with patch.object(billing, "_load_billing_credentials", return_value=creds), \
             patch.dict(sys.modules, {
                 "volcenginesdkcore": core_mod,
                 "volcenginesdkbilling": billing_mod,
             }):
            billing.query_balance()

        assert cfg.ak == "AKxx"
        assert cfg.sk == "SKyy"
        assert cfg.region == "cn-beijing"
        core_mod.Configuration.set_default.assert_called_once_with(cfg)
        api_instance.query_balance_acct.assert_called_once()

    def test_missing_sdk_raises_aibackend_error_mentioning_conda_env(self):
        creds = {"access_key": "AK", "secret_key": "SK", "region": "cn-north-1"}

        # Force the lazy import to fail as if the SDK weren't installed.
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("volcenginesdk"):
                raise ModuleNotFoundError(f"No module named '{name}'", name=name)
            return real_import(name, *args, **kwargs)

        with patch.object(billing, "_load_billing_credentials", return_value=creds), \
             patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(AIBackendError) as exc:
                billing.query_balance()

        assert exc.value.provider == "volc-billing"
        assert exc.value.retryable is False
        assert "chaoxing-backend" in str(exc.value)

    def test_api_failure_raises_aibackend_error(self):
        core_mod, billing_mod, api_instance = _make_fake_sdk(_fake_response())
        api_instance.query_balance_acct.side_effect = RuntimeError("signature invalid")
        creds = {"access_key": "AK", "secret_key": "SK", "region": "cn-north-1"}
        with patch.object(billing, "_load_billing_credentials", return_value=creds), \
             patch.dict(sys.modules, {
                 "volcenginesdkcore": core_mod,
                 "volcenginesdkbilling": billing_mod,
             }):
            with pytest.raises(AIBackendError) as exc:
                billing.query_balance()

        assert exc.value.provider == "volc-billing"
        assert "signature invalid" in str(exc.value)

    def test_config_error_propagates(self):
        # Missing credentials should surface as ConfigError, not AIBackendError.
        with patch.object(billing, "_load_billing_credentials",
                          side_effect=ConfigError("no creds")):
            with pytest.raises(ConfigError):
                billing.query_balance()


# ══════════════════════════════════════════════════════════════════
#  CLI — chaoxing.balance
# ══════════════════════════════════════════════════════════════════

class TestBalanceCLI:

    @pytest.fixture(autouse=True)
    def capture_stdout(self):
        self._buffer = io.StringIO()
        self._orig = sys.stdout
        sys.stdout = self._buffer
        yield
        sys.stdout = self._orig

    def _lines(self):
        self._buffer.seek(0)
        return [json.loads(l) for l in self._buffer.read().strip().split("\n") if l]

    def test_success_emits_single_balance_line(self):
        balance = {
            "accountId": 42,
            "availableBalance": "100.50",
            "cashBalance": "80.25",
            "creditLimit": "0.00",
            "arrearsBalance": "0.00",
            "freezeAmount": "5.00",
            "currency": "CNY",
        }
        with patch.object(balance_cli, "query_balance", return_value=balance):
            balance_cli.main()

        lines = self._lines()
        assert len(lines) == 1
        ev = lines[0]
        assert ev["type"] == "BALANCE"
        assert ev["provider"] == "doubao"
        assert ev["accountId"] == 42
        assert ev["availableBalance"] == "100.50"
        assert ev["cashBalance"] == "80.25"
        assert ev["creditLimit"] == "0.00"
        assert ev["arrearsBalance"] == "0.00"
        assert ev["freezeAmount"] == "5.00"
        assert ev["currency"] == "CNY"
        assert ev["checkedAt"].endswith("Z")

    def test_failure_emits_error_line_and_exits_1(self):
        err = AIBackendError("SDK missing, use Anaconda", provider="volc-billing")
        with patch.object(balance_cli, "query_balance", side_effect=err):
            with pytest.raises(SystemExit) as exc:
                balance_cli.main()

        assert exc.value.code == 1
        lines = self._lines()
        assert len(lines) == 1
        ev = lines[0]
        assert ev["type"] == "ERROR"
        assert ev["error"] == "SDK missing, use Anaconda"
        assert ev["detail"] == "AIBackendError"

    def test_config_error_surfaces_as_error_line(self):
        with patch.object(balance_cli, "query_balance",
                          side_effect=ConfigError("creds not found")):
            with pytest.raises(SystemExit):
                balance_cli.main()
        ev = self._lines()[0]
        assert ev["type"] == "ERROR"
        assert ev["detail"] == "ConfigError"
