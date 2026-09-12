"""
Chaoxing (超星学习通) 平台实现。

自原顶层包 chaoxing/ 迁入（M1 平台抽象重构），平台专属内容：
    platform/    登录 / 课程扫描 / 验证码 / 导航（passport2 / mooc1 域名与选择器）
    solvers/     章节测验求解器与内容完成 bot（.TiMu / knowledge/cards 等）
    font/        font-cxsecret 字体反解（超星特有）
    js/ data/    注入脚本与字体表等包内资产
    discover.py  课程发现（动态课程配置 + 断点状态）
    orchestrator.py  超星多账号编排（登录→扫描→测验/内容）
    api.py       JSON-line 协议入口（python -m platforms.chaoxing.api）
    accounts.py / courses.py / balance.py / ai_config.py  Electron 子命令入口

兼容入口：python -m chaoxing.api 等旧命令经由 backend/chaoxing/ 转发垫片继续可用。
"""

__version__ = "2.0.0"
