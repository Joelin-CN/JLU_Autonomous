"""超星平台常量：配置文件路径与包内资产目录。

通用路径与标志经 ``from core.constants import *`` 原样再导出（含 os/sys 等
模块属性，兼容 chaoxing.constants 旧契约）；此处只追加超星专属路径。
"""

from pathlib import Path

from core.constants import *  # noqa: F401,F403  (通用路径 + 进程标志 + 模块属性)
from core.constants import (  # noqa: F401  (显式列出供静态检查与 IDE)
    WORKSPACE, DATA_ROOT, SCRIPT_DIR, OUTPUT_DIR, TMP_DIR, LOG_DIR,
    SCREENSHOTS_DIR, CHROME_PROFILES_DIR, CREDS_DIR, DOCUMENTS_DIR,
    MAX_ACCOUNTS, SHUTDOWN_FLAG,
)

# ── 超星配置文件 ────────────────────────────────────────────────
CONFIG_PATH = WORKSPACE / "chaoxing_config.json"

# ── 包内资产（注入 JS / 字体表），随包分发、只读 ─────────────────
PACKAGE_DIR = Path(__file__).parent
JS_DIR = PACKAGE_DIR / "js"
DATA_DIR = PACKAGE_DIR / "data"
