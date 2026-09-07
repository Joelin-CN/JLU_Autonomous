# 外部脚本调研 + 站点实测 + 拟人化稳定性分析

日期：2026-08-14
范围：Userscript.Zone / GreasyFork / OpenUserJS / GitHub 刷课脚本调研；超星真实站点探索；
当前流程纰漏核对；拟人化/稳定性改造方案。

## 一、外部脚本调研

已下载并精读：

| 来源 | 仓库/脚本 | 可借鉴点 |
|------|-----------|----------|
| GitHub | `chaolucky18/xuexitongScript`（V3 稳定版） | 视频卡住/暂停自恢复（no-progress 看门狗）、有界重试、顺序播放、`#coursetree` 条件等待 |
| GitHub | `ahonn/soraka` | 服务端 `/ananas/status` + 播放日志上报、`isPassed` 完成语义、localStorage 断点续看 |
| GitHub | `luooofan/autochaoxing` | 章节测验提交间隔 120–150s 防验证码、`WebDriverWait` 条件等待、`scrollIntoView` 后点击 |
| GreasyFork | 超星网课助手 v4.7.10 | 提交时间随机化、完成检测轮询、`ans-job-finished` 状态判断 |

明确不吸收的激进策略：跳过人脸/验证码、伪造鼠标事件、秒刷播放日志、搜答案提交等。
本项目只采用常规限速、随机抖动、条件等待、可靠重试与完成检测。

## 二、真实站点探索

用项目同一套 playwright-cli + 持久化档案登录真实账号（132*** 等 3 个账号），核对：

- 登录页：`passport2.chaoxing.com/login`，表单为「手机号/超星号 + 学习通密码 + 登录」，
  现有 JS DOM 登录链路可用；登录后跳 `i.chaoxing.com/base`。
- 课程列表：个人空间 → 课程 → `mooc2-ans` iframe，课程卡片懒加载；
  **只滚动一次就抽取会把 11 门课抽成 1 门**（实测复现），需“滚动-等待-卡片数稳定”。
- 章节树：`mooc2-ans/mycourse/studentcourse` iframe，`div.chapter_item#cur{contentid}`
  与 `.catalog_title` 结构与扫描器假设一致；点小节后主页面跳到
  `mooc1.chaoxing.com/mycourse/studentstudy`。
- 视频小节：`knowledge/cards` iframe 暴露 `JC.attachments`，任务点状态文本
  `任务点已完成/未完成` 存在；播放器为 `video/index.html` + `video` 元素 +
  `.vjs-big-play-button`，与 `_v17_section_player.js` 假设一致。
- 账号文件：`CHAOXING_ACCOUNTS_FILE` 环境变量控制生效文件；前端标签需回读后端设置。

## 三、当前流程纰漏（本轮修复）

1. 课程扫描懒加载竞态：一次滚动即抽取 → 课程数丢失（修复：卡片数稳定轮询）。
2. 多账号并发探测 playwright 会话时 `playwright-cli list` 并发打同一守护 socket，
   造成 `list` 挂死、整条泳道卡在「检查浏览器会话」（修复：互斥锁 + 超时兜底）。
3. 账号失败仍报「执行完成」：子线程吞掉登录失败/崩溃（修复：结果收集 + `AccountRunError`）。
4. 内存采样把“无 Chrome 进程”当探测失败（修复：空结果输出 0）。
5. 账号增删改后 UI 列表因缓存不刷新；设置页账号文件标签不同步；登录网址列恒显“默认”。
6. 单课程任务在“课程完成、账号仍在跑后续阶段”时横幅提前 100%（修复：非账号级
   `DONE` 前封顶 99%，真正完成才置 100）。
7. 大量固定等待造成机器节律：关键路径加入随机抖动与条件等待（登录、扫描、导航、
   内容处理、答题提交、视频轮询）。

## 四、拟人化/稳定性改造清单

见 [STABILITY_HUMANIZE_FIX_2026-08-14.md](../fixes/STABILITY_HUMANIZE_FIX_2026-08-14.md)。
