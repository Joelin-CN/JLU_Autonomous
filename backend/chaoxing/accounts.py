"""兼容入口：``chaoxing.accounts`` → ``platforms.chaoxing.accounts``。"""
import importlib
import sys

_real = importlib.import_module("platforms.chaoxing.accounts")
if __name__ != "__main__":
    sys.modules["chaoxing.accounts"] = _real

if __name__ == "__main__":
    _real.main()
