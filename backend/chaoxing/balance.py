"""兼容入口：``chaoxing.balance`` → ``platforms.chaoxing.balance``。"""
import importlib
import sys

_real = importlib.import_module("platforms.chaoxing.balance")
if __name__ != "__main__":
    sys.modules["chaoxing.balance"] = _real

if __name__ == "__main__":
    _real.main()
