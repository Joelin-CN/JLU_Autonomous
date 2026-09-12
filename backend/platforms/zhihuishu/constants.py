"""智慧树平台常量：域名、URL 模式与 recruitAndCourseId 编码器。

编码算法（2026-09-12 实地破译并验证，见调研报告 §Q2）：
    明文 = f"{recruitId};{courseId}"
    密文 = hex( bytes[i] XOR key[i % len(key)] )，key = "zhihuishu"
"""

from pathlib import Path

from core.constants import WORKSPACE

# ── 配置 ────────────────────────────────────────────────────────
# M2 决策：智慧树复用 chaoxing_config.json 的通用段（playwright_cli /
# timeouts / retry / ai / max_concurrent），由 core.config 统一加载；
# 平台专属配置项（如需）在 M3+ 再拆分独立文件。
CONFIG_PATH = WORKSPACE / "chaoxing_config.json"

# ── 域名与页面 URL ──────────────────────────────────────────────
LOGIN_URL = "https://login.zhihuishu.com/?origin=zhs"
COURSE_LIST_URL = "https://onlineweb.zhihuishu.com/onlinestuh5"
STUDY_URL_BASE = "https://studyvideoh5.zhihuishu.com/stuStudy"

# ── 会话与目录命名 ──────────────────────────────────────────────
SESSION_PREFIX = "zhihuishu-chrome"
# Profile 目录由 core.browser.orphans.profile_dir_for_session 推导：
#   data/chrome-profiles/zhihuishu/account-N（与超星历史平铺路径隔离）
ACCOUNTS_FILE_ENV = "ZHIHUISHU_ACCOUNTS_FILE"
ACCOUNTS_FILE_NAME = "zhihuishu.txt"

# ── recruitAndCourseId 编码 ─────────────────────────────────────
_XOR_KEY = "zhihuishu"


def encode_recruit_and_course_id(recruit_id, course_id) -> str:
    """Encode ``recruitId;courseId`` into the stuStudy URL token.

    实测向量：("428215", "1000003834") →
    "4e5a515a445c4859454a5859584651405c"（学习页实际 URL 一致）。
    """
    plain = f"{recruit_id};{course_id}"
    key = _XOR_KEY
    return "".join(
        f"{ord(ch) ^ ord(key[i % len(key)]):02x}" for i, ch in enumerate(plain)
    )


def build_study_url(recruit_id, course_id) -> str:
    """Construct the shared-course study page URL for one course."""
    return f"{STUDY_URL_BASE}?recruitAndCourseId={encode_recruit_and_course_id(recruit_id, course_id)}"
