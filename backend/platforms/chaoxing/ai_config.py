"""Standalone AI connectivity test for the Electron AI panel.

Tests the provider configured via --provider (or chaoxing_config.json →
ai.provider as fallback): calls /models with the matching credentials file
and prints one JSON line.
"""

import json
import sys

from core.ai.doubao import _load_credentials, _PROVIDERS
from core.config import cfg
from core.logging_setup import log

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def _write(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, separators=(',', ':')))


def run_test() -> None:
    """Call the provider's /models endpoint, one JSON line out."""
    if OpenAI is None:
        _write({"type": "AI_TEST", "ok": False,
                "reason": "此解释器未安装 openai，请在设置中选择含 openai 的 Python"})
        sys.exit(1)
    provider = None
    if "--provider" in sys.argv:
        i = sys.argv.index("--provider")
        if i + 1 < len(sys.argv):
            provider = sys.argv[i + 1]
    if provider not in _PROVIDERS:
        provider = cfg("ai.provider", "doubao-api")
        if provider not in _PROVIDERS:
            provider = "doubao-api"
    try:
        spec = _PROVIDERS[provider]
        creds = _load_credentials(provider)
        client = OpenAI(base_url=spec["base_url"],
                        api_key=creds["api_key"], timeout=30, max_retries=0)
        models = client.models.list()
        log(f"AI connectivity test OK ({spec['label']}): "
            f"{len(models.data or [])} models", "OK")
        _write({"type": "AI_TEST", "ok": True, "models": len(models.data or [])})
    except Exception as e:
        log(f"AI connectivity test failed: {str(e)[:200]}", "ERROR")
        _write({"type": "AI_TEST", "ok": False, "reason": str(e)[:300]})
        sys.exit(1)


if __name__ == "__main__":
    run_test()
