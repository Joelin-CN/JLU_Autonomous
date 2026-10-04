"""平台 CLI 入口 argparse 冒烟测试。

背景（2026-09-13 真机联测发现）：为智慧树补内存参数时误删了 ``--job-id`` /
``--accounts`` 两个必选参数定义，pytest 全绿（无测试以 CLI 方式带参拉起入口）、
Electron mock 链路也不触发——只有真实 spawn 才会暴露。本测试用空 ``--accounts``
（两侧入口都在校验段快速失败、不打开浏览器）以完整参数集拉起两个平台入口，
锁定「Electron 注入的全部参数都必须被 argparse 接受」这一契约。

参数集与 ``frontend/electron/ipc/job.handler.ts`` job:start 的组装一一对应。
"""
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

# job.handler.ts 无条件注入的全部参数（--courses/--grade-only/--content-only
# 为可选注入，此处不传——空 accounts 在更早的校验段失败，效果等同）。
FULL_ARGSET = [
    "--job-id", "argparse-smoke",
    "--accounts", "",
    "--mode", "scan_only",
    "--max-concurrent", "1",
    "--budget-gb", "0.5",
    "--system-limit-gb", "200",
    "--per-account-estimate-gb", "0.7",
]


def _run_cli(module: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, *FULL_ARGSET],
        cwd=BACKEND, capture_output=True, text=True, timeout=60,
    )


def test_zhihuishu_cli_accepts_full_argset():
    result = _run_cli("platforms.zhihuishu.api")
    assert "unrecognized arguments" not in result.stderr, result.stderr
    assert "usage:" not in result.stderr, result.stderr
    # 空 --accounts 在校验段快速失败（不打开浏览器），错误经 NDJSON 输出
    assert "No valid account indices" in result.stdout


def test_chaoxing_cli_accepts_full_argset():
    result = _run_cli("platforms.chaoxing.api")
    assert "unrecognized arguments" not in result.stderr, result.stderr
    assert "usage:" not in result.stderr, result.stderr
    assert "No valid account indices" in result.stdout
