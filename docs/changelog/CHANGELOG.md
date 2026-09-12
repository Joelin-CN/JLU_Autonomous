# Changelog

本文件汇总各轮变更；历史明细见 [archive/](archive/) 下的原始 FIXLOG。

## 2026-09-12（续四）— 前端多平台 UI 重构：品牌通用化 + 平台一级维度 + 工单三形态

- **品牌通用化**：全部「超星助手 / Chaoxing Assistant」文案与标识改为「**JLU 学习助手**」（App 壳/侧栏/窗口标题/系统通知/index.html/`productName`/`appId→cn.edu.jlu.assistant`/`package.json name`）；`APP_NAME` 改 `jlu-study-assistant`（打包 userData 一次性 rename 迁移，开发模式不受影响）；localStorage key 迁移 `chaoxing-assistant-settings → jlu-study-assistant-settings`（读旧写新删旧）；接口名 `ChaoxingApi → AppApi`；图标暂沿用（无设计资源）。
- **平台一级维度（修 PR #3 三层断点）**：新增 `platform.store`（全局 `currentPlatform`，localStorage 持久化）+ 侧栏品牌区下方全局切换器（运行中禁切）+ 头部当前平台徽标 + 侧栏 footer 双平台状态行；撤销课程图谱页 view-local Tab。**账号/课程数据按平台分桶**（`Record<Platform, Account[]>` 与 `platform:accountId` 复合键，两平台行号不再互撞）；electron 主进程 `accounts:list` / `courses:scan` / `courses:list` / `accounts:add|edit|remove` 修复为消费已声明的 platform 参数（此前硬编码 chaoxing，切换器「看起来支持、数据仍是超星」）——不改任何 IPC 通道名。
- **能力矩阵驱动**：新增 `shared/lib/platforms.ts`（`PLATFORM_META` 徽标元数据 + `PLATFORM_CAPABILITIES`）；课程图谱任务按钮组按矩阵显隐/置灰——智慧树「全自动（视频）」文案、仅刷题/仅内容置灰并带「M4 开发中」tooltip；设置页账号表单「登录网址」字段仅超星显示；`passport2.chaoxing.com` 硬编码特判改平台注册表 `defaultLoginHost`。
- **工单三形态**：渲染层 `Ticket` 增 `timeoutSeconds` / `platform` / 判别 `kind`（`captcha` 输入型 / `qrcode` 扫码型 / `hint` 提示型），`mapElectronTicket` 透传新字段并按后端字段组合判别形态（扫码=图+timeoutSeconds；滑块=无图 captcha）；CaptchaModal 三形态（扫码型二维码大图+per-ticket 倒计时+扫码后自动继续，提示型文字+URL linkify）；主进程转发 `on-ticket` 时注入任务平台；关注队列加工单平台 tag + 平台过滤 pill + 申诉链接可点击。
- **视图与 mock**：仪表盘统计卡/账号点阵按平台分组（AI 余额卡保留全局）；执行页 banner 平台徽标；设置页账号面板平台 Tab（可分别管理两平台账号，路径 per-platform）；`maskPhone` 四份本地拷贝统一为 `shared/lib/mask.ts maskLogin`（学号等非手机号登录通用掩码）；mock 层按平台生成数据（超星手机号+mooc1 / 智慧树学号+onlineweb）并覆盖三形态工单，`__popCaptcha(kind)` DEV 钩子支持注入三形态。
- **验证（视觉+DOM 双确认）**：dev 模式 10 项交互流全部通过（切平台→账号列表换学号→按钮降级→扫码/滑块/输入工单弹出→平台持久化→旧 key 迁移删除），4 张截图经 vision 分析无阻塞缺陷；`npm run typecheck` 双 project 绿；vitest **31 passed**（新增 platforms 注册表/classifyTicketKind/settings 迁移/captcha 超时/mock 平台路由 5 组）；后端 `pytest tests/unit` 不回归。存量观察项（点阵图例色差、统计卡密度、工单平台 tag 图标）记录于 PR。

## 2026-09-12（续三）— M3 视频全链路实测通过（0.1 节 456/456s，全程无人值守）

- **实测结论（全部 DOM+视觉双确认）**：storageState 零扫码二次验证；章节树滚动加载 38 节点；**三种弹窗自动化**（学前必读=右上角X带重试、课程提醒=下次再说每轮清扫、弹题=试选→.answer 揭示→选正确→进度入账）；播放启动=真实点击 .videoArea（.bigPlayButton 需 hover 且悬停态跨 CLI 命令不保持，实测换路径）；**0.1 节 456/456s 原速完整播放**（.time_icofinish 标记），途中自动处理 2 弹题 + 2 课程提醒。
- **关键修复**：fixed 定位弹窗可见性判定（offsetParent 恒 null 致三类弹窗漏检，统一 rect+computedStyle）；播放/恢复点击改 .videoArea；观看循环每轮通用弹窗清扫。
- 回归 632 passed。

## 2026-09-12（续二）— M3 前置：storageState 登录态 / core 编排机上收 / 视频处理器（D6 原速策略）

- **storageState 登录态闭环（D5 对策）**：登录成功导出 `chrome-profiles/zhihuishu/account-N/storage-state.json`，任务启动注入 Cookie——实测第二轮**零扫码**（75 cookies 恢复→直接登录，34s 完成扫描 vs 首轮扫码 105s）。
- **core/orchestrator.py 上收**：多账号并发/内存门/泳道结果机制平台无关化（ModuleRunner 惰性 getattr，平台模块 monkeypatch 语义保留）；chaoxing 委托 core（测试全绿），zhihuishu api 接入（多账号并发生效）。
- **M3 视频处理器（platforms/zhihuishu/video.py，D6 决策）**：仅 1.0 倍速真实播放——不碰倍速菜单、播放/静音/下一节全走站点控件真实点击、观察 JS 只读（paused/currentTime）、4–7s 人味轮询、禁心跳伪造；含章节树滚动加载、锁课检测（跳过+申诉工单）、弹题「试选→.answer 揭示→改选」纯 DOM 处理。实测待可用课程。
- **回归**：629+3 passed（含 storageState 过滤与 D6 节奏单测）。

## 2026-09-12（续）— M2 智慧树平台包 + 前端 IPC 平台化

- **M2 后端**（`platforms/zhihuishu/`）：XOR 编码器（实测向量）、auth（扫码优先 + 密码/滑块兜底 + 会话管理）、scanner（课程列表 + 章节树 DOM 解析）、api（JSON-line 协议入口）、accounts/courses 子命令、`core/credentials.py` 通用凭据解析。**有头 Chrome 实测全链路 95s**：扫码→登录检测→课程扫描→章节树→JSON 落盘。
- **引擎修复（core）**：`--headed` 全局前缀致 headed 模式点击全灭（继承自超星的隐性 bug）；UTF-8 流包装 GC 关闭底层 buffer 致 pytest 静默崩溃（改 `reconfigure`）；新增 `core/browser/orphans.py` 通用孤儿清理。
- **前端 IPC 平台化**：`Platform` 类型 + `StartJobPayload.platform` 贯通 5 处 spawn 位（`platforms.<platform>.api/accounts/courses`）、`ZHIHUISHU_ACCOUNTS_FILE/HEADED` 环境注入、会话清理 `{platform}-chrome-*`、backendPath marker 与打包白名单适配 M1 布局。渲染层平台切换 UI 留待后续 PR（默认平台行为不变）。
- **实测发现（写入报告附录 D）**：智慧树登录 Cookie 会话级不落盘；章节树 el-scrollbar 懒加载；playwright-cli `--headed` 仅 open 子命令可用；主页存在登录链接干扰判定。
- **验证**：后端 629 passed / 前端 typecheck 全绿；验证清单 `VALIDATION_AFTER_ZHIHUISHU_M1M2_2026-09-12.md`。

## 2026-09-12 — 智慧树 M0 调研完成 + M1 平台抽象重构（core/ + platforms/）

- **M0 双轨调研完成**：`docs/reports/analysis/ZHIHUISHU_REFS_2026-09-12.md`（11 个 GitHub 项目 + 4 个 GreasyFork 脚本参考矩阵，标杆 = Autovisor/fuckZHS/Cooanyh）与 `ZHIHUISHU_ANALYSIS_2026-09-12.md`（Q1–Q8 全部落答 + 选择器「DOM+视觉」交叉确认清单）。关键实证：密码登录必触发易盾滑块且自动化环境被指纹检测拒绝（4 次实测）、扫码登录可行、学习页 URL 密文 = `hex(XOR("recruitId;courseId","zhihuishu"))` 已破译验证、**异常学习行为会锁课**（实测触发，已固化为工程红线）、2020 年油猴选择器词汇 2026 仍有效。技术路线决策 D2：浏览器自动化为主。
- **M1 平台抽象重构**：`backend/chaoxing/` 拆分为 `core/`（协议/引擎/内存/追踪/AI/工具，平台无关）+ `platforms/chaoxing/`（超星实现）+ `chaoxing/`（兼容垫片：sys.modules 别名表 + 5 个 `-m` 入口自替换转发，旧命令与 monkeypatch 语义完全不变）。引擎参数化：`core/browser/orphans.py` 通用孤儿 Chrome 清扫（按 profile 目录）、`profile_dir_for_session`（新平台按 `chrome-profiles/<platform>/account-N` 隔离，超星保持历史平铺路径）、`{PLATFORM}_HEADED` 环境变量（`CHAOXING_HEADED` 继续全平台生效）、日志文件名前缀可设（`set_log_file_prefix`）。
- **回归**：`python -m pytest tests/unit -q -s` 618 passed（零失败）；`python -m chaoxing.api --help` / `accounts list` 旧入口冒烟通过；`chaoxing.api is platforms.chaoxing.api` 模块同一性断言通过。
- **凭据**：新增 `data/passwords/zhihuishu.txt`（git 忽略；`{...}` 块格式，Q7 决策 D4）。

## 2026-09-07 — 仓库打底：迁移至 JLU_Autonomous 并建立协作规范

- **迁移**：项目自 [Chaoxing_auto](https://github.com/Joelin-CN/Chaoxing_auto)（基线 2026-08-27，commit `69847f6`）整体迁入本仓库，**未携带旧提交历史**（全新基线；旧仓库继续公开在线作为历史存档）。业务代码零改动。
- **定位升级**：README 重写为「JLU Autonomous —— 多平台自动学习助手」（超星 ✅ / 智慧树 🚧），新增平台支持矩阵与公开仓库声明。
- **协作规范**：新增 `CONTRIBUTING.md`（双管理者 @Joelin-CN / @Arthur-Pendrag0n 异步协作：feature 分支 + PR、Conventional Commits、刷课需求 Issue 认领制）；`AGENTS.md` 同步更新（git 工作流从单人直推 main 切换为 PR 制）。
- **文档体系**：新增 `docs/standards/`（directory / documents / secrets 三份规范）与 `docs/roadmap/zhihuishu.md`（智慧树路线图骨架，调研未开始）；`docs/README.md` 索引同步。
- **GitHub 配置**：新增 `.github/`（Issue 模板 ×3 含刷课需求模板与隐私警告、PR 模板、CODEOWNERS、CI 工作流：后端 pytest 单测 + 前端 typecheck/vitest）与根部 `SECURITY.md`；6 个协作标签（brush-request / status\* / platform\*）与 main 分支保护（PR + 1 approve + CI 门槛）已就位。
- **CI 首跑调通（4 轮）**：单测套件此前从未在全新克隆上运行过，CI 揭示并解决（仅改 workflow 与依赖清单，未动代码）：新克隆需 `chaoxing_config.example.json → chaoxing_config.json`、`data/{temp,output,logs}` 目录、`data/passwords/chaoxing.txt`（`{...}` 分块占位账号）与 `deepseek.txt` 占位密钥；playwright-cli 须装 `@playwright/cli`（npm 同名包为无 bin 废弃存根）；CI Python 对齐 3.13；`requirements-dev.txt` 补声明 `httpx`（存量缺口）。最终 CI 绿：后端 610 passed / 前端 typecheck + vitest 全过。
- **安全加固**：清理跟踪文件中的真实手机号 1 处（`docs/validation/VALIDATION_AFTER_FULLCHECK_2026-08-22.md`，改为「未打码」表述）；代码 / 测试中的同一号码示例替换为占位号段 `13200003918`（掩码后断言不变，相关单测验证通过）。`.gitignore` 补 `.zcode/`、`.superpowers/`、`.claude/plans/`、`.env*`。


## 2026-08-26（深夜二）— AI 引擎链路优化：DeepSeek 余额 + 切换保护

- **双余额显示**：仪表盘新增 DeepSeek 余额卡（官方免费接口
  `GET /user/balance`，仅需 httpx/openai 环境，不再依赖 volcengine SDK）；
  `chaoxing.balance --provider deepseek-api` + 前端 getBalance(provider)
  全链参数化；两引擎余额独立显示与刷新，实测 ¥99.49 / ¥97.40。
- **切换保护（三层）**：① 前端 AI_SET 运行中禁改（既有）；② quiz 级引擎
  锁定——引擎在 solve_quiz 入口解析一次，整个测验的所有批次与重试共用，
  中途切换只在下一测验生效（`_quiz_engine_fns`，含 None 回退）；③ 单请求
  原子性——_call_chat_completion 在调用开始加载凭证，请求内不受切换影响。
- 单测 +3（余额映射/不可用账户/引擎锁定源断言）；受影响文件相关测试
  分片全绿（用户游戏占内存致 24GB RAM 硬限偶发中断，与改动无关，
  零 failed）。

## 2026-08-26（深夜）— 新增 DeepSeek AI 引擎（deepseek-v4-flash-vision-exp）

- **后端**：doubao.py 抽出 `_PROVIDERS` 注册表（凭证文件/密钥变量/base_url），
  凭证加载、客户端工厂、chat 调用全部参数化；新增 `ai/deepseek.py` 薄壳复用
  全部批量/重试/解析管线（OpenAI 兼容 `https://api.deepseek.com`）；
  router 注册 `deepseek-api`；quiz solver 的 provider 白名单改查注册表；
  AIConfig 增加 deepseek 节（默认模型 deepseek-v4-flash-vision-exp）；
  ai_config 连通性测试支持 `--provider`。
- **凭证**：`data/passwords/deepseek.txt`（DEEPSEEK_API_KEY + model，git 忽略）。
- **前端**：设置页 AI 面板加引擎下拉（火山方舟/DeepSeek），切换只改
  chaoxing_config.json 的 ai.provider（不动各引擎密钥文件）；保存/连通性
  测试按当前引擎走对应凭证与校验（sk-/ark- 前缀）；ai.handler 全链泛化。
- **验证**：真实连通（3 models）；自绘题图识图解题（答对）；端到端
  答题链（概率论 4.6 章节测试2）：DeepSeek 解题 6 批 + 评分
  **100%（30✓/0✗）GRADE PASSED**；UI 切换/状态/测试/切回全链路；
  单测 +5（注册表/凭证解析/router 分派/provider 透传/旧 mock 修复），
  全量 **615 passed**。
- 文档：backend README 凭证格式与切换说明、example 配置 deepseek 节。

## 2026-08-26（晚）— daemon 卡死自愈链 + 一键扫描核查

- **daemon wedge 自愈（P1）**：长空闲后 daemon 卡死/Chrome 死亡导致课程
  FAILED。pw() 三级恢复（重试 → close+清孤儿+重开会话+就绪探测 → 再试）；
  死亡检测覆盖三类实测形态（超时 / stdout `### Error` rc=0 / stderr
  `is not open` rc=1）；quiz 与 content solver 导航失败时自动重进课程页
  （rebuild 落在 about:blank，章节树导航依赖课程上下文）；恢复日志落盘。
  实机验证：杀 Chrome 后测验完整恢复并 GRADE PASSED 100%（修复前同场景
  Solved 0 / Failed 11）；+9 单测（610 passed）。
- **一键扫描秒退核查（P2）**：洁净环境 ×3 未复现（任务均真实启动并写
  入发现文件）；加固 startJob 同步失败留痕（日志控制台中文原因）。
  详见 `VALIDATION_AFTER_WEDGE_SCAN_FIX_2026-08-26.md`。

## 2026-08-26 — 全流程功能枚举 + 刷课策略验证 + 发现文件数据丢失修复

- **修复（P1）**：带课程过滤的任务会用扫描子集覆盖 `discovered_courses_*.json`，
  导致未触及课程从总览消失（数据丢失）。`save_discovered_state` 新增 merge 语义
  （按 courseid 合并保留未触及课程，orchestrator 5 处调用按 `bool(args.course)` 启用；
  全量扫描仍整体覆盖以保留"已完成剔除"语义）。+3 单测（598 passed）；
  端到端验证 + 全量扫描恢复 10 门真实数据。
- 策略实效验证（模拟运行）：内容链（章节遍历/任务点检测/反爬延迟/不完成标记）
  与答题链（V2 截图 30/30、6 批 Doubao 解题、30 次 DOM click 填答、评分 100%
  GRADE PASSED、未提交）全链路核实；填答生效经像素级高亮检出三证确认。
- 功能枚举：五页面全部控件实机枚举通过（含深色主题/AI 连通/编辑弹窗）。
- 记录未修：playwright-cli daemon 运行中 wedge（长空闲后命令超时致课程 FAILED）；
  UI 一键扫描偶发秒退（未稳定归因）。详见
  `docs/validation/VALIDATION_AFTER_FULLFLOW_2026-08-26.md`。

## 2026-08-22（晚二）— 文档同步与死代码清理

- 文档同步：两份 README 与 `docs/design/api.md` 的 invoke 通道数 30 → 28
  （backend-settings 移除后遗留）；api.md 补 `system:validate-python` 通道、
  PHASE 事件的 PHASE_RANK 推导语义、PROGRESS 事件实际处理路径（原文描述的
  `updateProgress` 从未被调用）。
- 死代码清理：`execution.store.updateProgress`（零调用）、`campaign.store.forecast`
  与 `DEFAULT_FORECAST`/`CampaignForecast`（结果预测卡改真实数据后无消费者）。
- 验证：typecheck / vitest 11 passed / 双端构建；实机三页渲染抽检正常
  （执行概况空态、监控空态、10 课程卡）。

## 2026-08-22（晚）— 进度条真实性与动态性修复

来源：DOM+截图三时点核查发现三处"死"进度（详见
`VALIDATION_AFTER_PROGRESSBARS_2026-08-22.md`）。

- 阶段时间线修活：后端 PHASE 事件只带阶段名不带序号且与前端阶段文案
  两套词汇 → 时间线恒停第 0 项。主进程按 PHASE_RANK 映射更新
  `job.phaseIndex`（唯一真理源），渲染层每次按其重算并即时打 ✓；
  running 阶段内进度条改为 CSS 流动动画（后端无每阶段分数，恒 0% 是误导），
  ProgressBar 补 `role=progressbar`/`aria-valuenow`。
- 终态清理：完成 → 全部 ✓；失败 → running ✕；停止 → running ⏹（此前停止后
  时间线残留「运行中」）。
- 关注队列「结果预测」为常量假数据（50 项/M2/75% 恒不变）→ 改为「执行概况」
  真实数据：整体进度条、运行席位 x/y、真实工单数、状态与耗时。
- 课程总览：卡片进度是扫描快照（设计如此），运行中账号卡片加「运行中」角标。
- `ipcClient.getJobStatus` 不再回放 startJob 时的 phases 陈旧副本。

验证：阶段跨入 process_sections 后 ✓×3 + running 推进（DOM + 识图双口径）；
关注队列 36%→81% 实时变；停止 ⏹；typecheck/vitest/构建通过；清理无回归。

## 2026-08-22 — 全流程检查修复批次（5 P1 + 9 P2）

来源：`VALIDATION_AFTER_FULLCHECK_2026-08-22` 全流程检查（静态 + 实机）发现的问题，
修复明细与验证见 `VALIDATION_AFTER_FULLCHECK_FIX_2026-08-22.md`。

### P1 修复
- **Python 启动秒败 UI 永远「运行中」**：根因是 `pythonBridge` 合成事件写死
  `jobId:'main'` 被 store 过滤器丢弃。修复：bridge 携带真实 jobId；`exit` 路径
  （进程秒退）也显式推送 `ON_ERROR`；ENOENT 译为中文指引；执行监控挂载时与
  主进程状态对账；store 终态时把仍在「运行中/排队/暂停」的泳道标记为终态并显示
  原因。实测伪解释器场景 6 秒内横幅「执行失败」、泳道「异常」+ 中文原因。
- **真实配置随安装包分发**：`electron-builder.yml` 白名单改打包
  `chaoxing_config.example.json`；首启 seeding 找不到真配置时回退复制 example。
  重建包实测：example 在、真实配置不在。
- **打包缺省内存参数**：白名单加入 `.playwright/cli.config.json`，打包版保留
  Chromium 降内存 flags（重建包实测在）。
- **Python 解析统一 + 设置校验**：新增 `electron/python/resolve.ts` 共享解析器
  （env 覆盖 → 设置 → PATH），5 条 spawn 路径统一走它；余额报错在渲染层剥离
  `Error invoking remote method` 包装、仪表盘显示真实中文原因；设置页保存与输入
  时双重校验 pythonPath（存在性 + Python ≥3.10 探测，新增 `system:validate-python`
  通道）；账号列表加载失败进日志控制台（原先静默空列表）。
- **playwright-cli 缺失无引导**：后端 `engine.pw()`/`auth` 调用点前置
  `ensure_cli_available()`（带缓存），缺失时抛中文指引（npm i -g playwright-cli），
  兼容 shell=True 的「不是内部或外部命令」检测。

### P2 修复
- 执行席位手机号脱敏（`132****3918`，新增共享 `mask.ts`）。
- 「模拟运行」开关持久化到设置（`dryRun`），切视图/重启不再静默复位。
- 课程总览「一键扫描/一键全自动」支持账号子集（选中 ≥1 即可用）。
- `CHAOXING_TIMEOUT_SECTION_COMPLETE` 由前端注入（新增设置项「章节完成超时」）。
- `job:status` 无参回退当前任务；未找到/无任务的报错改中文；`job:start` 重复启动、
  同步 spawn 失败报错改中文。
- 移除无人调用且与 `settings:get/set` 完全重复的 `backend-settings:get/set` 通道
  （invoke 通道 30 → 28）。
- 仪表盘「运行时长」标签改为「系统运行」（实为 os.uptime() 语义）。
- 新增 `backend/requirements-dev.txt`（pytest、pillow）。
- 文档同步：`docs/design/api.md` 环境变量白名单表补全 12 项；backend README
  测试数（595）与模块数（47）更新、补依赖安装说明。

### 验证
- 后端单测 595 passed（新增 7 个 CLI 可用性用例）；前端 vitest 11 passed
  （新增 mask/错误清洗 9 例）；typecheck 与双端构建通过。
- 实机复测（CDP 驱动真实界面）：余额中文原因、设置校验拒绝伪路径、脱敏、
  dryRun 跨重启持久化、单账号子集启动、伪解释器 6 秒失败不卡死、job:status
  中文报错、真实运行（登录→扫描→停止）无回归、Chrome 清理 chrome.exe = 0。

## 2026-08-14（收尾）— Chrome 残留清理 / 0-0 课程语义 / 逐步骤识图核查

### 修复
- Chrome 进程残留：Electron `closeBrowserSessions` 的 `.cmd` 调用补 `shell:true`，
  关闭后再按 profile 根定向清理残留 chrome.exe；后端 close 增加 1s 等待 + 孤儿进程清扫，
  open 前也先清扫。实测停止任务后 chrome.exe = 0、`playwright-cli list` 为空。
- 0/0 课程误判：`discover_courses` 对课程卡片显示 0/0 的课程也做真实章节树扫描；
  实际已完成（如大学物理ABC（上）103/103）从工作列表剔除，有任务的课程恢复真实
  章节/进度，真空课程保持 0/0。

### 调研与验证
- 0/0 课程语义经 DOM + 识图交叉确认（无任务 / 已完成 / 卡片未渲染进度三种情况）。
- 后端主要链路逐步骤真实运行并识图核查 6 张截图：登录、课程列表、章节树、
  内容小节、答题页填答（30 题 100% AI 评分、未提交）。
- 后端单元测试 588 passed；前端类型检查通过。

## 2026-08-14 — 稳定性与拟人化改造（外部脚本调研 + 站点实测）

### 修复
- 账号级失败不再误报成功：`run_multi_account` 收集线程结果，登录失败/线程崩溃抛
  `AccountRunError`；`api.py` 对用户停止发 `stopped + ERROR + DONE`。
- 内存采样：无 Chrome 进程时输出 0，不再报 `Memory sampler degraded`。
- 账号增删改后列表即时刷新（`refreshAccounts` 绕过 `loaded` 缓存）；设置页账号文件
  标签回读后端；账号列表带真实登录网址。
- 课程扫描：卡片懒加载“滚动-等待-数量稳定”后再抽取（修复 11 门被抽成 1 门）。
- 多账号并发探测 playwright 会话串行化 + 超时兜底（修复 `playwright-cli list` 挂死）。
- 停止后重启不再复用死会话；运行中进度在账号级 `DONE` 前封顶 99%。
- 视频播放器：20s 无进度自恢复看门狗、播放失败有界重试、轮询抖动。
- 关键路径固定等待改为随机抖动（登录、扫描、导航、内容处理、答题提交）。
- 真实提交模式章节测验间 60–120s 随机间隔，降低触发提交验证概率。

### 验证
- 后端单元测试 587 通过；前端类型检查通过。
- 真实界面 E2E（真实账号、模拟运行不提交）28/28 通过。
- 识图（vision）复核：修复识图服务超时后，16 张关键截图逐张核对与断言一致，
  含修复前「执行完成 100% vs FAILED」矛盾截图与修复后「执行失败」对照。

## 2026-08-13（续二）— 账号解析 / CLI / 状态机修复

### 修复
- 多账号凭证解析崩溃：`read_all_chaoxing_credentials()` 对无 `[N]` 下标的后续账号块
  执行 `max(str) + 1` 抛 `TypeError`；改用独立整数索引集合分配序号。
- `website[N]` 写入后无法读回：`_parse_credential_block()` 只识别无下标的 `website`；
  现在兼容 `website[N]` / `网站[N]`，账号增删改不再丢自定义登录网址。
- CLI shim 完全失效：`scripts/chaoxing_orchestrator.py` / `utils.py` / `chapter_*`
  import 已删除符号；重建向后兼容入口，ps1 的 P/Q 改走 stdin 信号
  （`PAUSE`/`RESUME`/`STOP`），batch-test 参数名修正为 `--section`；并修复
  `Read-Host` 起始章节提示缺少闭合引号导致的 ps1 语法错误。
- Electron 失败任务被 `DONE` 翻转为 `completed`；旧任务 `exit`/`error` 事件误清新任务
  状态；全局清理增加“当前 bridge”守卫。
- 无凭证/无匹配账号时后端误报成功：`api.py` 启动前预检凭证与账号索引，失败发
  `ERROR + DONE`。
- 默认 Python 路径去除 `E:\Softwares\...` 硬编码（空 = PATH 上的 python）；退出清理
  改为按 `data/` 根过滤的定向进程清理；删除会污染账号数据的 `refreshAccountStatus`
  死代码。
- 前端类型清理：Electron `Settings` 移除 `deepseekModel` / `doubaoModel` /
  `autoResolve` 残留，`quizSolver` 统一为 `doubao`。

### 文档
- 同步根 README / frontend README / backend README / api.md / integration.md /
  API_SPEC.md（Store 9 个、IPC 30+8、真实数据接入现状、`--chromium-flags` 移除、
  `MEMORY` 事件、测试数 584）；architecture.md / API_REFERENCE.md /
  auto-solution-design.md 加历史参考横幅。

## 2026-08-13（续）— 设置项落地与文档校正

### 新增
- 「浏览器与系统」设置：Python 解释器路径、页面加载/快照/点击/视频观看/答题
  五项超时、日志保留天数；超时与重试通过 `CHAOXING_TIMEOUT_*` /
  `CHAOXING_RETRY_*` 环境变量注入后端（`config.py` 同时覆盖 legacy `cfg()` 与
  类型化配置）。
- 任务完成/异常时按「系统通知」开关推送 Electron 桌面通知；应用启动时按
  「日志保留」清理 `data/logs/*.log`。
- 前端关键设置操作（保存 AI 配置、账号增删改、切换账号文件、内存计划失败）
  写入日志面板与后端每日日志（账号掩码、密钥不落盘）。

### 移除
- 死开关：`autoResolveCaptcha` / `autoResolve`（后端无消费）、`videoSpeed`、
  `sectionDelay`（无后端对应），从类型与设置页摘除；验证码仍由后端按需自动
  识别，失败走人工工单。

### 文档
- 三份 README 与 `docs/design/api.md` 同步：`--chromium-flags` 移除、动态并发
  公式、新增 IPC 通道与 `MEMORY` 事件、deepseek-web 已不支持、真实数据接入
  现状、测试数量 578。

## 2026-08-13 — 前端鲁棒性与内存感知并发

### 新增
- 设置页新增「AI 推理 · 火山方舟」：API Key + 模型 ID 写入本地
  `doubao.txt`（原子写 + 备份 + 尾号回显）+ 方舟连通性测试。
- 账号管理 UI：增删改账号直接写入当前生效账号文件，支持自定义账号文件路径
  （文件选择器 + 恢复默认 + 解析校验）；删除不重排、新增复用空位。
- 内存感知并发：启动前按 `(总内存 − 基线) × 75%` 与 CPU 线程数动态计算最大并发，
  运行中每 5 秒实测 Chrome 进程树持续收紧，超预算账号自动排队分批跑完；
  `MEMORY` 事件驱动预算仪表与「排队中」通道状态。

### 修复
- `--chromium-flags` 从未到达 Chrome 的问题：省内存参数改经
  `.playwright/cli.config.json` 真实生效（GPU 进程 ~100MB → ~38MB）。
- `playwright-cli open` 传带 `&` 的登录 URL 被 cmd 截断：改为 `about:blank`
  打开后经 `pw_goto` 导航。
- 后端绝对 RAM 护栏（20/22/24G）改为任务级相对阈值；并发上限不再写死为 10。

## [Unreleased] — 2026-08-07 目录规范化与迁移修复

### 修复
- 清理旧盘硬编码路径：`chaoxing_config.json` 移除失效的 `workspace_root`（旧路径 `E:/B306/...` 已不存在），代码中不再读取该字段。
- Python 解释器引用改为便携写法：新增专用 conda 环境 `chaoxing-backend`（含 `volcengine-python-sdk`），`balance.py` / `billing.py` / 文档中的 `E:/Softwares/Anaconda/python.exe` 全部替换为环境激活方式或 `CHAOXING_BALANCE_PYTHON` 覆盖。
- 修复 `solver.py` 把临时 JS / 截图写入源码包目录的问题（统一写入 `data/temp/`）。
- 修复 `electron-builder.yml` 未排除 `chrome-profiles/`（登录态 cookie）、`screenshots/`、`documents/`、`etc/`、`tests/` 的打包隐患：改为白名单只打运行时必需文件。

### 目录规范化（对齐 monorepo 规范）
- 运行时产物迁至仓库根 `data/`：`passwords/`、`chrome-profiles/`、`screenshots/`、`output/`、`temp/`、`logs/`、`documents/`（全部 git 忽略）。
- 第三方参考脚本迁至 `references/`（git 忽略，仅索引）。
- `docs/` 重构为 `design/`（api / integration / architecture / reference）、`changelog/`、`reports/analysis/`、`sessions/`、`validation/`、`logs/`，并新增 [docs/README.md](../README.md) 索引。
- 新增 `AGENTS.md`、`.gitattributes`、`data/README.md`、`references/README.md`、`backend/chaoxing_config.example.json`；真实 `chaoxing_config.json`、`backend/.claude/plans/`、`backend/etc/`、`backend/documents/` 移除 git 跟踪。

### 工程
- 新增环境变量 `CHAOXING_DATA_DIR`（运行产物根，默认 `<仓库>/data` 或 `userData/data`），前端 `backendPath.ts` / `pythonBridge` / 各 IPC handler 同步透传。
- 前端默认 Python 路径指向 `chaoxing-backend` 环境（可在设置中覆盖）。
- 清理跟踪的临时垃圾文件 `chaoxing/solvers/quiz/tmp90t7oahm.js`。

## 历史归档

| 日期 | 文档 | 内容 |
| --- | --- | --- |
| 2026-06-26 | [FIXLOG_20260626_vue-tsc_typecheck.md](archive/FIXLOG_20260626_vue-tsc_typecheck.md) | vue-tsc 工具链升级 & 类型检查修复 |
| 2026-06-26 | [FIXLOG_20260626_balance_query.md](archive/FIXLOG_20260626_balance_query.md) | 余额查询功能接入 |
| 2026-06-26 | [FIXLOG_20260626_apiclient_singleton.md](archive/FIXLOG_20260626_apiclient_singleton.md) | API 客户端单例化 |
| 2026-06-25 | [FIXLOG_20260625_security_stability.md](archive/FIXLOG_20260625_security_stability.md) | 安全漏洞修复 & 稳定性加固 |
| 2026-06-24 | [FIXLOG_20250624_headed_e2e.md](archive/FIXLOG_20250624_headed_e2e.md) | Headed 模式全流程 E2E 验证 |
| 2026-06-24 | [FIXLOG_20250624_e2e_backend_verify.md](archive/FIXLOG_20250624_e2e_backend_verify.md) | 后端重构验证 + 多账户 E2E |
| 2026-06-24 | [FIXLOG_20250624_bat_ps1_modes.md](archive/FIXLOG_20250624_bat_ps1_modes.md) | BAT/PS1 六模式修复 |
| 2026-06-24 | [CHANGELOG_20250624.md](archive/CHANGELOG_20250624.md) | 全脚本优化日志 |
| 2026-06-23 | [DEEPSEEK_FIXES.md](archive/DEEPSEEK_FIXES.md) | DeepSeek 自动解题模块修复 |
| 2026-06-23 | [FIXLOG.md](archive/FIXLOG.md) | CLI Panel 重构 + 多账户 |
