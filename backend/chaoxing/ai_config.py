"""兼容入口：``chaoxing.ai_config`` → ``platforms.chaoxing.ai_config``。"""
import importlib
import sys

_real = importlib.import_module("platforms.chaoxing.ai_config")
if __name__ != "__main__":
    sys.modules["chaoxing.ai_config"] = _real

if __name__ == "__main__":
    _real.main()
