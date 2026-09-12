"""
Volcano Engine (火山引擎) account balance query — Billing OpenAPI backend.

Queries the cash/account balance of the Volcano Engine account that owns the
Doubao (豆包) inference resources. This is SEPARATE from the Ark inference
endpoint used by ``doubao.py``:

    - doubao.py   -> Ark inference (ark.cn-beijing.volces.com), ARK_API_KEY,
                     returns per-request token usage only — NO balance.
    - billing.py  -> Billing OpenAPI (open.volcengineapi.com), AK/SK + V4 HMAC
                     signing, returns the account cash balance.

SDK: volcengine-python-sdk (>= 5.0.0). The import name is NOT ``volcengine`` —
each cloud service lives under ``volcenginesdk<service>``. The billing service
is ``volcenginesdkbilling``; core config/auth is ``volcenginesdkcore``.

IMPORTANT — lazy import: the SDK is only installed in the dedicated
``chaoxing-backend`` conda environment, NOT in every interpreter that runs the
unit tests. The SDK is therefore imported *inside* ``query_balance()`` so this
module imports cleanly under any interpreter (matching the lazy-import pattern
in ``doubao.py``).
"""

import re

from ..exceptions import ConfigError, AIBackendError
from ..constants import CREDS_DIR

CREDS_FILE = CREDS_DIR / "volc_billing.txt"

DEFAULT_REGION = "cn-north-1"
PROVIDER = "volc-billing"


# ══════════════════════════════════════════════════════════════════
#  Credentials
# ══════════════════════════════════════════════════════════════════

def _load_billing_credentials() -> dict:
    """Parse VOLC_ACCESS_KEY / VOLC_SECRET_KEY (and optional region) from
    passwords/volc_billing.txt.

    File format (both shell-export and plain env syntax accepted)::

        export VOLC_ACCESS_KEY="AK..."
        export VOLC_SECRET_KEY="SK..."
        region="cn-north-1"     # optional, defaults to cn-north-1

    Returns:
        dict with keys: access_key, secret_key, region.

    Raises:
        ConfigError: file missing, or AK/SK could not be parsed.
    """
    if not CREDS_FILE.exists():
        raise ConfigError(
            f"Volcano billing credentials not found: {CREDS_FILE}\n"
            f"Create data/passwords/volc_billing.txt with VOLC_ACCESS_KEY and "
            f"VOLC_SECRET_KEY (see docs/design/api.md)."
        )

    content = _read_creds_file()

    def _extract(name: str) -> str:
        # Quoted form first (export KEY="..."), then bare form (KEY=value).
        m = re.search(rf'{name}\s*=\s*"([^"]+)"', content)
        if not m:
            m = re.search(rf'{name}\s*=\s*(\S+)', content)
        return m.group(1).strip() if m else ""

    access_key = _extract("VOLC_ACCESS_KEY")
    secret_key = _extract("VOLC_SECRET_KEY")
    region = _extract("region") or DEFAULT_REGION

    if not access_key:
        raise ConfigError(
            f"Could not parse VOLC_ACCESS_KEY from {CREDS_FILE}. "
            f'Expected format: VOLC_ACCESS_KEY="AK..."'
        )
    if not secret_key:
        raise ConfigError(
            f"Could not parse VOLC_SECRET_KEY from {CREDS_FILE}. "
            f'Expected format: VOLC_SECRET_KEY="SK..."'
        )

    return {"access_key": access_key, "secret_key": secret_key, "region": region}


def _read_creds_file() -> str:
    """Read the credentials file, tolerating UTF-8 or ANSI/GBK text.

    Chinese Windows editors (e.g. Notepad) often save plain text files as
    ANSI/GBK; decoding strictly as UTF-8 would fail or garble the values.
    """
    for encoding in ("utf-8", "gbk"):
        try:
            return CREDS_FILE.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ConfigError(
        f"Could not decode credentials file {CREDS_FILE} as UTF-8 or GBK. "
        "Re-save it as plain ANSI/UTF-8 text."
    )


# ══════════════════════════════════════════════════════════════════
#  Balance query
# ══════════════════════════════════════════════════════════════════

def query_balance() -> dict:
    """Query the Volcano Engine account cash balance via the Billing OpenAPI.

    Loads AK/SK from passwords/volc_billing.txt, configures the SDK, and calls
    ``BILLINGApi.query_balance_acct``. The SDK is imported lazily so this module
    can be imported (and tested) under interpreters where the SDK is absent.

    Returns:
        Normalized camelCase dict::

            {"accountId": int, "availableBalance": str, "cashBalance": str,
             "creditLimit": str, "arrearsBalance": str, "freezeAmount": str,
             "currency": "CNY"}

    Raises:
        ConfigError: credentials missing/invalid.
        AIBackendError: SDK not installed (retryable=False, message points to
            Anaconda), or the API call failed.
    """
    creds = _load_billing_credentials()

    # Lazy import — the SDK only exists in the Anaconda interpreter.
    try:
        import volcenginesdkcore
        import volcenginesdkbilling
    except ModuleNotFoundError as e:
        raise AIBackendError(
            "volcengine-python-sdk is not installed in this interpreter "
            f"({e.name}). The balance query must run under an interpreter that "
            "has the SDK installed (activate the dedicated conda env, e.g. "
            "`conda activate chaoxing-backend && python -m chaoxing.balance`).",
            provider=PROVIDER,
            retryable=False,
        ) from e

    try:
        cfg = volcenginesdkcore.Configuration()
        cfg.ak = creds["access_key"]
        cfg.sk = creds["secret_key"]
        cfg.region = creds["region"]
        volcenginesdkcore.Configuration.set_default(cfg)

        api = volcenginesdkbilling.BILLINGApi()
        resp = api.query_balance_acct(
            volcenginesdkbilling.QueryBalanceAcctRequest()
        )
    except Exception as e:
        raise AIBackendError(
            f"Volcano billing API call failed: {type(e).__name__}: {e}",
            provider=PROVIDER,
            retryable=False,
        ) from e

    return _normalize_balance(resp)


def _normalize_balance(resp) -> dict:
    """Map a QueryBalanceAcctResponse to the camelCase contract dict."""
    return {
        "accountId": getattr(resp, "account_id", None),
        "availableBalance": getattr(resp, "available_balance", None),
        "cashBalance": getattr(resp, "cash_balance", None),
        "creditLimit": getattr(resp, "credit_limit", None),
        "arrearsBalance": getattr(resp, "arrears_balance", None),
        "freezeAmount": getattr(resp, "freeze_amount", None),
        "currency": "CNY",
    }
