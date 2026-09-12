"""
Core -- 平台无关的自动化基础设施层。

从原 chaoxing 包抽取的通用能力，供 platforms/ 下各平台实现复用：

    constants       路径与进程级标志（WORKSPACE / DATA_ROOT / 输出目录 / SHUTDOWN_FLAG）
    config          ConfigManager 与超时 / 重试 / AI 配置模型（dot-notation cfg() 兼容）
    session         线程本地浏览器会话名管理（"{platform}-chrome-N"）
    logging_setup   log/progress/phase/ticket 协议桥 + 信号量 + RAM 守卫
    memory          内存计划 / 准入门 / EWMA 监视器（PowerShell 采样）
    tracking        断点续跑状态（per-session JSON）
    browser         playwright-cli 引擎（engine / js_runner / viewport / orphans）
    ai              AI 答题路由与后端（doubao / deepseek，平台无关）
    utils           通用工具（human_delay / 快照 ref 查找）
    exceptions      异常层次（历史根类 ChaoxingError，见模块内说明）

平台实现（platforms/chaoxing、platforms/zhihuishu）不放进 core；
新增代码禁止在 core 内出现平台专属选择器 / 域名 / 课程 ID 语义。
"""

__version__ = "2.0.0"
