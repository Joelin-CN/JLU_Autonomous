"""兼容入口：``chaoxing.api`` → ``platforms.chaoxing.api``（自替换转发）。

``python -m chaoxing.api`` 时以 __main__ 执行本文件并调用真实 main()；
``import chaoxing.api`` 时把 sys.modules 中的本模块替换为真实模块对象，
保证新旧路径共享同一模块状态（monkeypatch / 模块级全局一致）。
"""
import importlib
import sys

_real = importlib.import_module("platforms.chaoxing.api")
if __name__ != "__main__":
    sys.modules["chaoxing.api"] = _real

if __name__ == "__main__":
    _real.main()
