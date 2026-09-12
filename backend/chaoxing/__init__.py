"""
Chaoxing 兼容垫片（compat shim）— M1 平台抽象重构。

真实实现已迁移：
    平台无关层 → backend/core/
    超星平台实现 → backend/platforms/chaoxing/

本包只做转发，保证旧入口继续可用：
    - ``python -m chaoxing.api``（Electron / CLI 旧调用方）
    - ``from chaoxing.xxx import ...``（scripts/ 与旧测试）

原理：导入本包时把 ``chaoxing.*`` 逐一别名到 ``sys.modules`` 中新位置的
同一模块对象（非拷贝），因此 monkeypatch 与模块级状态在新旧路径下完全
一致。新代码一律直接使用 ``core.*`` / ``platforms.chaoxing.*``。
"""

import importlib
import sys

__version__ = "2.0.0"
__author__ = "Chaoxing Automation Project"

_ALIASES = {
    # ── 平台无关层 → core/ ──
    "chaoxing.constants": "platforms.chaoxing.constants",  # 含 core 通用路径再导出 + 平台资产路径
    "chaoxing.config": "core.config",
    "chaoxing.exceptions": "core.exceptions",
    "chaoxing.logging_setup": "core.logging_setup",
    "chaoxing.session": "core.session",
    "chaoxing.memory": "core.memory",
    "chaoxing.tracking": "core.tracking",
    "chaoxing.utils": "core.utils",
    "chaoxing.browser": "core.browser",
    "chaoxing.browser.engine": "core.browser.engine",
    "chaoxing.browser.js_runner": "core.browser.js_runner",
    "chaoxing.browser.viewport": "core.browser.viewport",
    "chaoxing.browser.orphans": "core.browser.orphans",
    "chaoxing.ai": "core.ai",
    "chaoxing.ai._base": "core.ai._base",
    "chaoxing.ai.doubao": "core.ai.doubao",
    "chaoxing.ai.deepseek": "core.ai.deepseek",
    "chaoxing.ai.prompts": "core.ai.prompts",
    "chaoxing.ai.router": "core.ai.router",
    "chaoxing.ai.billing": "core.ai.billing",
    # ── 超星平台实现 → platforms/chaoxing/ ──
    "chaoxing.platform": "platforms.chaoxing.platform",
    "chaoxing.platform.auth": "platforms.chaoxing.platform.auth",
    "chaoxing.platform.captcha": "platforms.chaoxing.platform.captcha",
    "chaoxing.platform.navigation": "platforms.chaoxing.platform.navigation",
    "chaoxing.platform.scanner": "platforms.chaoxing.platform.scanner",
    "chaoxing.solvers": "platforms.chaoxing.solvers",
    "chaoxing.solvers.quiz": "platforms.chaoxing.solvers.quiz",
    "chaoxing.solvers.quiz.solver": "platforms.chaoxing.solvers.quiz.solver",
    "chaoxing.solvers.quiz.extractor": "platforms.chaoxing.solvers.quiz.extractor",
    "chaoxing.solvers.quiz.filler": "platforms.chaoxing.solvers.quiz.filler",
    "chaoxing.solvers.quiz.grader": "platforms.chaoxing.solvers.quiz.grader",
    "chaoxing.solvers.quiz.retry": "platforms.chaoxing.solvers.quiz.retry",
    "chaoxing.solvers.quiz.stats": "platforms.chaoxing.solvers.quiz.stats",
    "chaoxing.solvers.quiz.strategies": "platforms.chaoxing.solvers.quiz.strategies",
    "chaoxing.solvers.quiz.submitter": "platforms.chaoxing.solvers.quiz.submitter",
    "chaoxing.solvers.content": "platforms.chaoxing.solvers.content",
    "chaoxing.solvers.content.bot": "platforms.chaoxing.solvers.content.bot",
    "chaoxing.solvers.content.detector": "platforms.chaoxing.solvers.content.detector",
    "chaoxing.solvers.content.handlers": "platforms.chaoxing.solvers.content.handlers",
    "chaoxing.solvers.content.navigator": "platforms.chaoxing.solvers.content.navigator",
    "chaoxing.font": "platforms.chaoxing.font",
    "chaoxing.discover": "platforms.chaoxing.discover",
    "chaoxing.orchestrator": "platforms.chaoxing.orchestrator",
}

# 注意：5 个 CLI 入口模块（api / accounts / courses / balance / ai_config）
# 不走别名表——runpy 执行 ``python -m chaoxing.api`` 时若 chaoxing.api 已被
# 预注册会与 loader 冲突。它们由同名的入口文件以"自替换"方式转发
# （导入时将 sys.modules["chaoxing.api"] 替换为真实模块对象）。

for _alias, _target in _ALIASES.items():
    sys.modules[_alias] = importlib.import_module(_target)
