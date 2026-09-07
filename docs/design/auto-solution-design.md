# 超星学习通 — 自动化课程完成方案

> 生成时间: 2026-06-21 | 更新: 2026-06-24 | 账号: 林琦沅 | 学校: 重庆邮电大学

> ⚠️ **历史参考（2026-06）**：DeepSeek 双引擎已移除，AI 仅支持 Doubao API；入口与最新架构见
> [api.md](api.md) / [architecture.md](architecture.md)。

---

## 一、课程总览

| # | 课程 | 教师 | 任务点 | 完成率 | 章节测试 | 作业 | 考试 | 难度 |
|---|------|------|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 大学物理ABC（下） | 罗小兵 | 0/88 | 0% | ❌ 无 | 暂无 | ❌ 无 | ⭐ 低 |
| 2 | 综合英语-2025 | 牟之渝等 | 0/77 | 0% | ❌ 无 | 未查 | 5个全过期 | ⭐ 低 |
| 3 | 概率论与数理统计 | 鲜思东 | 79/100 | 79% | ✅ 16个 | 暂无 | 全完成/过期 | ⭐⭐ 中 |

**总计待完成: 0 + 0 + 21 = 21 个任务点**（大学物理88个 + 综合英语77个 + 概率论21个 = 共计186，但物理和英语可能无法自动完成内容型任务点）

---

## 二、逐课程详细结构

### 2.1 大学物理ABC（下）— 0/88 (0%)

**URL**: `courseid=214594847&clazzid=127342628`

**章节结构**: 7章，29节课，全部内容型（视频/文档）

| 章节 | 课时数 | 任务点分布 |
|------|:---:|---|
| 1. 静电场 | 7 (1.1~1.7) | 2+2+2+2+2+2+0 = 12 |
| 2. 静电场中的导体与电介质 | 3 (2.1~2.3) | 4+4+4 = 12 |
| 3. 恒定磁场 | 5 (3.1~3.5) | 2+2+2+2+4 = 12 |
| 4. 电磁感应 电磁场 | 5 (4.1~4.5) | 4+5+4+4+5 = 22 |
| 5. 相对论 | 3 (5.1~5.3) | 4+4+4 = 12 |
| 6. 量子力学基础 | 4 (6.1~6.4) | 4+4+4+3 = 15 |
| 7. 课外阅读观看材料 | 2 (7.1~7.2) | 3+0 = 3 |

**其他 Tab**:
- 任务: 暂无任务
- 讨论: 2个教师帖（不占任务点）
- 作业: 暂无作业 (0/0)
- 考试: **无此 Tab**
- 资料: 参考文献

**自动化策略**: 
逐节点击 → 等待视频播放 / 文档滚动 → 检测完成标记(绿勾) → 下一节。
⚠️ 88节课量极大，预计耗时 4-6 小时自动化运行。

---

### 2.2 综合英语-2025 — 0/77 (0%)

**URL**: `courseid=254993142&clazzid=127285559`

**章节结构**: 5单元，20节课，全部内容型

| 单元 | 课时 | 任务点 |
|------|------|:---:|
| Unit 1: The Digital Age | 4 (Warm-up, Text A&B, Enjoying English, Listening) | 3+6+4+2=15 |
| Unit 2: Life Stories | 4 | 3+6+3+2=14 |
| Unit 3: Let's Go | 4 | 9+6+2+2=19 |
| Unit 4: When Work is a Pleasure | 4 | 6+8+3+1=18 |
| Unit 5: China's Space Dream | 4 | 3+6+0+2=11 |

**关键发现**:
- 任务: 0进行中 / 10已结束（全部"随堂练习"已过期）
- 考试: 5个 Dictation 全部**已过期**
- 讨论: 待确认
- 作业: 待确认

**自动化策略**: 
与大学物理类似 — 逐节点击完成。77个任务点量大，预计 4-5 小时。

---

### 2.3 概率论与数理统计 — 79/100 (79%) ⚡

**URL**: `courseid=255106367&clazzid=127207872`

**剩余21个任务点全部在章节中**:

| 章节 | 剩余任务 | 类型 |
|------|:---:|---|
| 1. 概率论的基本概念 | 1.6章节测试1(1) + 1.7章节测试2(1) + 1.8课程思政(2) | 测验×2 + 内容×1 |
| 2. 随机变量及其分布 | 2.6第二章测试1(1) + 2.7第二章测试2(1) | 测验×2 |
| 3. 多维随机变量 | 3.7章节测试1(1) + 3.8章节测试2(1) | 测验×2 |
| 4. 数字特征 | 4.5章节测试1(1) + 4.6章节测试2(1) | 测验×2 |
| 5. 大数定律 | 5.3章节测试1(1) + 5.4章节测试2(1) + 5.5课程思政(2) | 测验×2 + 内容×1 |
| 6. 总体与样本 | 6.4章节测试1(1) + 6.5章节测试2(1) | 测验×2 |
| 7. 参数估计 | 7.5章节测试1(1) + 7.6章节测试2(1) + 7.7课程思政(1) | 测验×2 + 内容×1 |
| 8. 假设检验 | 8.5章节测试1(1) + 8.6章节测试2(1) | 测验×2 |
| 9. 随机过程 | 待确认（9.4 练习与测试） | 内容 |

**其他 Tab**:
- 任务: 暂无任务
- 作业: 暂无作业 (0/0)
- 考试: 第二次阶段测试补测(已过期) + 2个已完成
- 讨论: 待确认

**自动化策略（核心课程）**:
1. 课程思政/案例 (3个) → 点击阅读
2. 章节测试 (16个) → 打开 → 提取题目 → AI解答 → 提交 → 检查分数 → 若<100%则查看答案重试

---

## 三、任务类型分类

| 类型 | 出现次数 | 课程 | 自动化难度 |
|------|:---:|------|:---:|
| 视频课时 | ~45节 | 大学物理, 综合英语 | ⭐ 简单 |
| 文档/文本课时 | ~15节 | 全部 | ⭐ 简单 |
| 听力练习 | ~5节 | 综合英语 | ⭐⭐ 中等 |
| 课程思政/案例 | 3个 | 概率论 | ⭐ 简单 |
| **章节测试（选择/判断）** | **16个** | 概率论 | ⭐⭐ 中等 |
| **章节测试（含简答）** | **待确认** | 概率论 | ⭐⭐⭐ 较高 |

---

## 四、策略矩阵

| 任务类型 | 自动策略 | 关键操作 | 重试机制 |
|---------|---------|---------|:---:|
| 视频课时 | playwright: 点击课时 → 等待播放器加载 → 等待视频自然播完 或 快进到末尾 → 检测绿勾 | `click` → `waitForSelector(.completion-mark)` | ✅ 自动 |
| 文档课时 | playwright: 点击课时 → 滚动到页面底部 → 等待完成标记 | `click` → `evaluate(scrollTo bottom)` → 检测完成 | ✅ 自动 |
| 听力练习 | playwright: 点击课时 → 播放音频 → 等待结束 → 如有选择题则解答 | 组合视频+测验策略 | ✅ 自动 |
| 课程思政 | playwright: 点击 → 滚动阅读 → 检测完成 | 同文档策略 | ✅ 自动 |
| 章节测试 | playwright: 点击测试 → snapshot 提取题目 → AI 解答 → 填入答案 → 点击提交 → 检查得分 → 重试 | `extractQuestions()` → `aiSolve()` → `fillAnswers()` → `submit()` | ✅ 无限次 |
| 讨论 | playwright: 读取话题 → AI 生成回复 → 点击发布 | `readTopic()` → `aiReply()` → `post()` | ✅ |

---

## 五、风险评估

```
风险等级      | 任务                                   | 原因
-------------|---------------------------------------|--------------------------
🟢 低风险    | 视频课时, 文档课时, 课程思政              | 纯浏览操作，无失败惩罚
🟡 中低风险  | 听力练习                               | 可能含内嵌选择题
🟡 中风险    | 章节测试(选择/判断)                     | 需正确答题，但可无限重试
🟠 中高风险  | 章节测试(含简答)                        | 简答题需生成内容+可能人工批改
🔴 高风险    | 考试 (限时+限次)                        | 当前无待完成考试，风险已消除
```

---

## 六、推荐执行顺序

### 阶段一：概率论与数理统计（优先，收益最大）⚡
```
1. 打开 课程思政/教学应用案例 (1.8, 5.5, 7.7) → 阅读完成 (+5 任务点)
2. 逐章完成 章节测试 (16个) → 每题解答提交 (+16 任务点)
   - 策略: 先 snapshot 提取全部题目 → AI 批量解答 → 逐题填入 → 提交
   - 若得分 < 100%: 查看正确答案 → 重试
3. 完成 9.4 练习与测试（如有任务点）
目标: 79→100 (完成课程!)
```

### 阶段二：大学物理ABC（下）（大规模内容）
```
1. 逐章逐节点击完成
   - 每个视频课时: 等待视频加载+播完
   - 每个文档课时: 滚动到底
   预计 4-6 小时自动运行
```

### 阶段三：综合英语-2025（大规模内容）
```
1. 逐单元逐节点击完成
   - Warm-up Activity: 交互内容
   - Text A&B: 长文档阅读
   - Listening: 音频播放
   预计 4-5 小时自动运行
```

---

## 七、脚本架构（实际实现）

> **2026-06-24 重构**: 原始 `scripts/` 平面结构已重构为 `chaoxing/` Python 包（41 个模块，12 个子包）。`scripts/` 保留为向后兼容 shim，实际逻辑位于 `chaoxing/` 子包中。

```
chaoxing/                          # Python 包（41 个模块，12 个子包）
├── __init__.py                    # 包元数据 (v2.0.0)
├── constants.py                   # 全局路径、锁、标志位
├── config.py                      # 类型化配置（dataclass 模型）
├── discover.py                    # 课程发现 + 动态配置构建
├── exceptions.py                  # 类型化异常体系（10 个异常类）
├── logging_setup.py               # 结构化日志 + 键盘监听
├── orchestrator.py                # 顶层多线程编排器
├── session.py                     # 线程本地会话管理
├── ai/                            # 可插拔 AI 求解器后端
│   ├── _base.py                   # AISolver ABC
│   ├── doubao.py                  # Doubao API（OpenAI SDK，默认）
│   ├── deepseek.py                # DeepSeek Web（浏览器自动化）
│   ├── router.py                  # Provider 工厂 + 便捷包装
│   └── prompts.py                 # 统一提示词模板
├── browser/                       # Playwright CLI 封装层
│   ├── engine.py                  # pw(), pw_snapshot(), pw_click(), pw_goto()
│   ├── js_runner.py               # JS 注入（temp 文件 + pw_run_code_file）
│   └── viewport.py                # 视口尺寸管理
├── platform/                      # 超星网站特定逻辑
│   ├── auth.py                    # 多账户凭证解析 + 登录
│   ├── captcha.py                 # 验证码检测 + AI 识别
│   ├── navigation.py              # 课程 URL 构建 + iframe 快照
│   └── scanner.py                 # 课程/章节 DOM 发现
├── solvers/                       # 课程自动化执行
│   ├── quiz/                      # 答题子系统（5 层降级）
│   │   ├── solver.py              # ChapterQuizSolver 门面
│   │   ├── extractor.py           # 题目提取（DOM/截图）
│   │   ├── filler.py              # 答案填入表单
│   │   ├── grader.py              # 提交后批改（Grade-Only 模式）
│   │   ├── retry.py               # 基于分数的重试循环
│   │   ├── stats.py               # QuizStats 准确率追踪
│   │   ├── strategies.py          # 5 层策略调度
│   │   └── submitter.py           # 原生表单提交
│   └── content/                   # 内容完成子系统
│       ├── bot.py                 # ChapterContentBot 编排器
│       ├── detector.py            # 内容类型检测
│       ├── handlers.py            # 视频/音频/文档处理器
│       └── navigator.py           # 章节间导航
├── tracking/                      # 运行时状态持久化
│   └── __init__.py                # ProgressTracker（断点续传）
├── font/                          # 字体混淆解密
│   └── __init__.py                # Typr.js + MD5 font-cxsecret
├── utils/                         # 纯工具函数
│   └── __init__.py                # 快照解析、文本清洗
├── data/                          # 静态数据文件
│   └── _table.json                # 字形→字符映射表 (355KB)
└── js/                            # JS 注入文件
    ├── _v17_section_player.js     # 视频顺序播放器 (v17)
    ├── _v11_phase2_fallback.js    # 视频播放器 (旧版 v11)
    ├── _v10_js_combined.js        # 视频播放器 (更旧版 v10)
    ├── _decrypt_font.js           # 字体解密引擎
    ├── _resize_vp.js              # 视口缩放
    └── _debug_innertext.js        # 调试工具

scripts/                           # 向后兼容 shim（import 转发到 chaoxing.*）
├── chaoxing_config.json           # 配置文件（共享路径）
├── chaoxing_orchestrator.py       # → chaoxing.orchestrator
├── utils.py                       # → chaoxing 子模块（多模块）
├── chapter_quiz_solver.py         # → chaoxing.solvers.quiz.solver
├── chapter_content_bot.py         # → chaoxing.solvers.content.bot
├── deepseek_web.py                # → chaoxing.ai.deepseek
├── doubao_api.py                  # → chaoxing.ai.doubao
├── _solve_captcha.py              # → chaoxing.platform.captcha
├── _batch_nav.py                  # → chaoxing 子模块
├── _nav_to_course.py              # → chaoxing 子模块
├── *.js                           # JS 文件（保留副本）
├── _table.json                    # 字体映射表（保留副本）
├── data/output/                   # 运行时产物
├── data/temp/                     # 临时文件
├── data/logs/                     # 按日滚动日志
└── data/passwords/                # 凭证
```

### 核心 Python 依赖
- `playwright` (通过 playwright-cli CLI 调用, 非 Python API)
- `openai` (Doubao API 使用 OpenAI SDK 兼容接口)
- Python 3.10+（推荐 conda 环境 `chaoxing-backend`，余额查询需 `volcengine-python-sdk`）

### 顶层 CLI 入口
```
chaoxing_cli.bat  →  chaoxing_cli.ps1  →  Python 包 / 兼容 shim
  (启动器)              (交互菜单+路由)      (编排+执行)
```

### 调度器 (chaoxing/orchestrator.py) 职责
- 多账户并行 (threading.Thread, 每账户独立 Chrome session)
- 动态课程发现 (chaoxing/discover.py — scan_courses + scan_course_sections)
- 按配置顺序调度 (Phase 1 QuizSolver → Phase 2 ContentBot)
- 断点续传 (ProgressTracker + --resume)
- 超时/异常处理与恢复
- 键盘监听暂停/退出 (P/Q 文件标志位)

---

## 八、需要注意的边界情况

1. **网络延迟**: 章节页面通过 iframe 加载，需等待 iframe ready
2. **ref 过期**: 每次 tab 切换后 ref 会变，必须重新 snapshot
3. **视频自动播放**: Chaoxing 视频通常自动播放，自动标记完成。可能需处理弹窗/暂停
4. **章节测试题目类型**: 需逐个打开确认 — 单选(radio)、多选(checkbox)、判断(true/false)、简答(textarea)
5. **验证码**: 章节测试通常无验证码。如出现 slider/captcha，需人工介入
6. **重试限制**: 章节测试可无限重试(已确认)，但每次重试题目可能变化
7. **已过期任务不可恢复**: 综合英语-2025 的10个随堂练习和5个听写考试已过期，无法完成
8. **已结束课程**: 4门已结束课程不在自动化范围内
