"""
Zhihuishu (智慧树/知到) 平台实现 —— M2 范围：登录态 + 课程/章节扫描。

复用 core/ 基础设施（browser 引擎 / JSON-line 协议 / 内存治理 / AI 路由），
平台专属内容（域名 / 选择器 / 编码）只出现在本包内。

模块：
    constants    域名与 URL 常量、recruitAndCourseId 编码器
    navigation   页面导航与 URL 构造
    auth         浏览器会话与登录（扫码优先 / 密码+易盾滑块兜底）
    scanner      课程列表与章节树 DOM 解析
    discover     课程发现编排与状态持久化
    api          JSON-line 协议入口（python -m platforms.zhihuishu.api）
    accounts     zhihuishu.txt 凭据子命令
    courses      已发现课程查询子命令

工程红线（见 ZHIHUISHU_ANALYSIS_2026-09-12.md §Q5）：
    只用真实点击；禁止页面内 monkey-patch / evaluate 驱动媒体；
    倍速 ≤1.25（M3）；窗口不最小化。
"""

__version__ = "0.1.0"
