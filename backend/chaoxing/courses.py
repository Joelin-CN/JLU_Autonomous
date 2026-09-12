"""兼容入口：``chaoxing.courses`` → ``platforms.chaoxing.courses``。"""
import importlib
import sys

_real = importlib.import_module("platforms.chaoxing.courses")
if __name__ != "__main__":
    sys.modules["chaoxing.courses"] = _real

if __name__ == "__main__":
    _real.main()
