# 智慧树（知到）支持 · M0 调研报告（Track A + Track B 合流）

> **状态：✅ M0 完成**（2026-09-12）。本文为路线图 M0-C 产出物：双轨调研合流报告，Q1–Q8 全部落答，技术路线决策见 §9（ADR D2）。
>
> 调研方式：Track A 现有实现扫描（见 `ZHIHUISHU_REFS_2026-09-12.md` 参考矩阵）+ Track B 实地勘察（真实账号登录，DOM 快照 / 截图像素分析 / 事件实测）。
>
> **本文档所有账号均为占位形式（如 `13200003918`），真实测试账号仅存于 `data/passwords/zhihuishu.txt`。**

---

## 1. Q1 登录方式与登录态维持 ✅

| 项 | 结论 | 来源 |
| --- | --- | --- |
| 登录入口 | `https://login.zhihuishu.com/?origin=zhs`（passport.zhihuishu.com 会重定向到此，标题「登录中心」） | 实测 |
| 登录方式 | 账号登录 / 学号登录 / 工号登录 / 扫码 四个 Tab（Element Plus `el-tabs`） | 实测 |
| 表单选择器 | 手机号 `input[name="mobile"].el-input__inner`；密码 `input[type="password"]`；登录钮 `div.btn-block__grandient_login`（注意站点把 gradient 拼成 grandient）；协议复选框原生 `input.el-checkbox__original` **不可见**，须点 `label.privacy-checkbox`（或其内 `span.el-checkbox__inner`） | 实测 |
| 验证码 | 密码登录 **100% 触发网易易盾滑块**（弹窗 `.yidun_modal`，拼图缺口 + `.yidun_slider` 拖钮；隐藏字段 `NECaptchaValidate`） | 实测 |
| 滑块自动化 | 内嵌自动化浏览器（CDP/无 stealth）下**无法通过**：缺口位置计算正确（截图像素边缘检测 + 拼图 PNG alpha 内偏移，误差 <2px）、三种轨迹（缓动拟人 / Autovisor 随机分段 / 过冲回正）均被拒 → **环境指纹检测**而非位置/轨迹问题 | 实测 4 次 |
| 扫码登录 | **可行且已实测成功**：切「扫码」Tab → `img`（170×170，data URL）→ 知到 APP 扫码确认 → 跳转 `www.zhihuishu.com`，登录态建立 | 实测 |
| 登录态维持 | Cookie 会话 + 浏览器持久化 profile（与超星同思路）；异地登录会触发短信验证（fuckZHS 佐证） | 实测 + Track A |
| API 侧 | 密码登录接口被验证码卡死（fuckZHS：`validateAccountAndPassword` 返回 -4 需验证码；-2 密码错；-9 需短信） | Track A |

**工程结论**：登录降级链 = 持久 profile 已登录直进 → 扫码（二维码截图走 CAPTCHA 工单 + 用户 APP 确认）→ 密码 + 滑块（自动求解在有头 Chrome 下另行专项验证，兜底人工工单）。

## 2. Q2 课程与章节数据获取 ✅

- **课程列表**：`https://onlineweb.zhihuishu.com/onlinestuh5`（Vue3 SPA）。四个课程域：共享课 / 翻转课 / 兴趣课 / 智慧课程（M2 只做共享课，其余留枚举接口）。
- **课程卡片**：`dl > dt > .item-left-course`（`.courseName` 课程名、`.teacherName` 师资、`.process > .processNum` 进度百分比）；封面 `dd > .dd-in > img`；卡片无 href，点击卡片本身进入（Vue 点击处理）。
- **课程标识**：`recruitId`（选课 ID）+ `courseId`（课程 ID），见卡片区链接（成绩分析 `stuonline.../stuLearnReportNew/index?recruitId=&courseId=`）。
- **学习页 URL**：`https://studyvideoh5.zhihuishu.com/stuStudy?recruitAndCourseId=<密文>`。
  **密文算法（本次破译并实测验证）**：`hex( XOR("recruitId;courseId", "zhihuishu"循环) )`，如 `428215;1000003834` ↔ `4e5a515a445c4859454a5859584651405c`（编码器进入 `platforms/zhihuishu/constants.py`）。与 fuckZHS 的 `ev` 编码同族（旧播放器 key 即 `zhihuishu`）。
- **章节树**：`.box-right > .chapterScrollbar > .el-scrollbar__wrap > .el-scrollbar__view > ul.list`：
  - 章标题 `li.chapter > span.catalogue_title3 > b`（章号）+ `span.catalogue_title`（章名）
  - 视频节 `li.video`（当前节多 `.current_play`；节号 `b.pl5.hour`；标题 `span.catalogue_title[title]`；时长在 `b.time_ico_half` 区域）
  - 章测入口 `li.chapter-test[title="点击测试"] > span.name`（文案「平时测试」）
- **智慧课程（新域）**：`ai-smart-course-student-pro.zhihuishu.com/singleCourse/knowledgeStudy/<id>/<id>`（M2 不做）。
- **结论**：课程/章节数据 **DOM 解析即可，无需签名接口**；接口直连路线端点与签名详见 REFS §1 fuckZHS 行（后备）。

## 3. Q3 视频完成上报 ✅（Track A 双源交叉，浏览器路线无需伪造）

- 知到共享课（zhidao）：watchPoint 每 **1.99s** 追加；`totalStudyTime += 5×rate`、`videoProgress += 4.99×rate` 每 **4.99s**；`saveDatabaseIntervalTime(V2)` 每 **30–120s** POST（fuckZHS 用 30s 并停用 18s 缓存上报）。
- hike 校内课：`saveStuStudyRecord` 每 **30s**，MD5 签名（salt `o6xpt3b#Qy$Z`），响应 `rt` 重置计数器。
- 完成阈值 **~0.91**（`end_thre`）；服务端接受 >1x 倍速（即倍速原理），但异常倍速是风险信号。
- **浏览器路线结论**：真实播放器自行上报，自动化只需保证：真实播放（可信事件）、窗口不最小化/标签不后台（节流停滞，Autovisor 实证）、倍速克制（≤1.25）。
- 本次实测注记：在学习页注入 fetch/XHR 监听 + `evaluate` 驱动 `video.play()` 后 **45s 内被踢出并锁课**（见 Q5）——浏览器侧网络观测应走 Playwright 网络层（CDP 级，对页面不可见），**禁止页面内 monkey-patch**。

## 4. Q4 弹题 / 章节测验 / 作业 ✅

| 层 | 选择器 / 接口 | 备注 |
| --- | --- | --- |
| 弹题容器 | `.el-dialog__wrapper.dialog-test`（旧）/ `.el-dialog`（新） | 实测页面为 Element 系 |
| 弹题选项 | `.topic-list .topic-option-item` / `.topic-item` | 题型 `.title-tit`（【单选题】等） |
| **答案揭示** | 试点一项后正确答案暴露在 `.answer span` → 取消错选、改点真答案 | 406653 技巧；API 侧 `lessonPopoupExam` 直接返回 `opt.result=='1'`（双源佐证） |
| 弹题关闭 | `.el-dialog__footer .btn` / Escape | — |
| 章测入口 | 章节树 `li.chapter-test[title="点击测试"]` | 实测 |
| 作业页 | `stuExamWeb`：`.examPaper_subject .subject_describe` 题干、`.examquestions-answer` 选项、`.subject_node input` | Track A |
| 掌握度/新学习域 | `studywisdomh5.zhihuishu.com`：`.item-box(.gray/.pink)`、`.question-item`、`.el-radio/.el-checkbox`、`.submit` | Cooanyh（2026-09 活跃） |
| 题型抽象 | 单选/多选/判断/填空（+ essay 留空） | 与超星 solvers `single/multi/judge/fill/essay/unknown` 同构，AI 路由直接复用 |
| 考试 | 普遍不被脚本支持（风控强：后台 10s `updateUserUsedTime` 计时线程） | **M 阶段不做考试** |

## 5. Q5 反自动化手段 ✅（本地实测，含代价）

按严重度排列：

1. **异常学习行为 → 课程锁定（实测触发）**：在学习页做网络监听注入 + `evaluate` 驱动播放后，弹窗「平台监测到你存在异常学习行为，已将你的该门课程锁定…不再允许学习」，课程被锁（异常记录页 `onlineh5.zhihuishu.com/subPage.html#/student/exceptionRecordList`，四类：视频学习/见面课/考试/验证异常，含「我的申诉」入口）。触发面推测：不可信事件（`isTrusted=false` 的 play）、页面上下文 monkey-patch、自动化环境指纹。
2. **登录易盾滑块 + 环境检测**（见 Q1）：内嵌自动化浏览器 4 次全拒；真实 Chrome + stealth 下 Autovisor 证明可过（OpenCV 定位 + 随机分段轨迹）。
3. **「检测到异常脚本」踢出**：强制跳回首页（ocsjs #177 文档 + 本地复现）。
4. **播放器反调试**：`debugger` 冻结、`toString()` 自校验、控制流扁平化——**不要对在线播放器做 CDP 深度调试**。
5. **行为信号**：倍速异常、0.91 阈值、后台标签节流、异地登录短信。

**工程红线（写入实现约束）**：①只用 Playwright 真实点击（可信事件）；②禁止页面内 monkey-patch / evaluate 驱动媒体；③倍速 ≤1.25 且 UI 标签同步；④窗口不最小化；⑤拟人随机停顿；⑥浏览器侧网络观测只走 Playwright 网络层。

## 6. Q6 参考实现时效性 ✅

见 `ZHIHUISHU_REFS_2026-09-12.md`（11 个 GitHub 项目 + 4 个 GreasyFork 脚本矩阵）。要点：活跃且可用 = Autovisor（2026-09-07）、Cooanyh（2026-09-01）、ocsjs（2026-07）；2020 年选择器词汇 2026-09 本地实测仍有效；fuckZHS 协议知识有效但接口路线维护成本高。

## 7. Q7 凭据组织 ✅

分平台文件：`data/passwords/zhihuishu.txt`（`{...}` 块格式，`website` 默认 `https://login.zhihuishu.com/?origin=zhs`；中文别名 账号/密码/网站 沿用超星解析器约定）。测试账号已录入。

## 8. 路线对比（Q8 决策输入）

| 维度 | 浏览器自动化 | 接口直连 | 混合 |
| --- | --- | --- | --- |
| 登录 | profile 持久化 + 扫码 ✅ | 密码接口死，需扫码 token | 同左 |
| 签名/加密维护 | 无（页面自己算） | ev/AES 随前端 JS 轮换，易碎 | 双份 |
| 心跳 | 播放器原生上报 | 伪造全链路 | — |
| 资源占用 | 高（有 Chrome） | 极低 | 高 |
| 与现有架构契合 | **完全复用 engine/RAM 治理/工单** | 全新栈 | 部分 |
| 风控面 | 行为检测（可纪律化规避） | 签名检测 + 行为检测 | 最大 |

## 9. 决策记录（ADR，同步至路线图 §8）

- **D2（2026-09-12）**：技术路线取**浏览器自动化为主**（Autovisor 模式：真实 Chrome + 持久 profile + stealth + 真实事件），接口知识（fuckZHS）仅作后备优化储备。依据：Q1 密码 API 已死 / Q2 DOM 解析已足够 / 现有基础设施完全复用 / 选择器词汇 6 年稳定。
- **D3（2026-09-12）**：反自动化纪律为 P0 工程红线（Q5 §5 条）；滑块自动求解列为独立专项（有头 Chrome 下开发验证，人工工单兜底先行）。
- **D4（2026-09-12）**：凭据分平台文件 `data/passwords/zhihuishu.txt`。

## 附录 A：关键页面 URL 模式

| 页面 | URL |
| --- | --- |
| 登录 | `https://login.zhihuishu.com/?origin=zhs` |
| 学生首页（课程列表） | `https://onlineweb.zhihuishu.com/onlinestuh5` |
| 共享课学习页 | `https://studyvideoh5.zhihuishu.com/stuStudy?recruitAndCourseId=<XOR-hex>` |
| 成绩分析 | `https://stuonline.zhihuishu.com/stuonline/stuLearnReportNew/index?recruitId=&courseId=` |
| 见面课 / 课程资料 | `stuonline.zhihuishu.com/stuonline/teachMeeting/stuListV2?recruitId=` / `folder/stuIndexV2` |
| 问答 | `https://qah5.zhihuishu.com/qa.html#/web/home/<courseId>?role=2&recruitId=` |
| 异常记录 / 申诉 | `https://onlineh5.zhihuishu.com/subPage.html#/student/exceptionRecordList` |
| 智慧课程（新，M2 外） | `ai-smart-course-student-pro.zhihuishu.com/singleCourse/knowledgeStudy/<id>/<id>` |

## 附录 B：选择器「DOM + 视觉」交叉确认清单

> 工作流：DOM 证据（选择器/层级/rect/elementFromPoint 命中）+ 视觉证据（截图 → 本地 vision 识别）双确认后进入代码。状态：✅ 双确认 / 🔶 仅 DOM（视觉确认留待 M2 有头 Chrome 实测）。

| 目标 | 选择器 | DOM 证据 | 视觉证据 | 状态 |
| --- | --- | --- | --- | --- |
| 登录-手机号 | `input[name="mobile"]` | id `el-id-*-19`，placeholder 实测 | 表单区可见 | ✅ |
| 登录-密码 | `input[type="password"]` | 实测 | 同上 | ✅ |
| 登录-协议勾选 | `label.privacy-checkbox`（点 label，原生 input 不可见） | 原生 input 无点击点，实测 | 复选框在表单下方 | ✅ |
| 登录-提交 | `div.btn-block__grandient_login` | 实测唯一 | 渐变大按钮 | ✅ |
| 登录-扫码 Tab | `el-tabs` 第 4 个 `.el-tabs__item`（文本「扫码」） | 实测 | Tab 行最右 | ✅ |
| 滑块弹窗 | `.yidun_modal` / `.yidun_bg-img`(480→400) / `img.yidun_jigsaw`(91→76) / `.yidun_slider` | 坐标实测 | 截图像素分析 | ✅ |
| 课程卡 | `dl>dt>.item-left-course>.courseName`（+ `.processNum`） | 层级链实测 | 列表区可见 | ✅ |
| 章节-章 | `ul.list>li.chapter>span.catalogue_title3>b` + `span.catalogue_title` | HTML 实测 | 右侧目录区 | ✅ |
| 章节-视频节 | `ul.list>li.video`（`.current_play`）`b.pl5.hour`/`span.catalogue_title[title]` | HTML 实测 | 同上 | ✅ |
| 章节-章测 | `li.chapter-test[title="点击测试"]` | HTML 实测 | 同上 | ✅ |
| 播放器根 | `.box-left>#outContainer>.able-player-container>.video-js#vjs_container>video.vjs-tech` | 层级实测 | 左侧播放区 | ✅ |
| 播放/暂停 | `#playButton>.bigPlayButton.pointer`（暂停时可见） | HTML 实测 | 🔶 播放态视觉确认留 M2 | 🔶 |
| 下一节 | `#nextBtn.nextButton` | HTML 实测 | 🔶 同上 | 🔶 |
| 进度 | `.progressBar>.passTime`（width %）+ `.currentTime`/`.duration` | HTML 实测 | 🔶 同上 | 🔶 |
| 倍速 | `.speedBox>span` + `.speedTab[rate]`（1.0/1.25/1.5） | HTML 实测 | 🔶 同上 | 🔶 |
| 音量 | `.volumeBox .volumeIcon` / `.passVolume` | HTML 实测 | 🔶 同上 | 🔶 |
| 弹题 | `.el-dialog(.dialog-test)` + `.topic-item` + `.answer span` | Track A 双源 | 🔶 M2 实测 | 🔶 |
| 学习页弹窗-课程提醒 | `.el-dialog__wrapper.dialog-warn`（`.talk-later-btn`/`.rlready-bound-btn`） | 实测（公众号绑定提醒） | 弹窗可见 | ✅ |
| 学前必读弹窗 | `.preschool-Mustread-div`（内含 Chart canvas） | 实测（曾遮挡播放器） | 🔶 M2 复核 | 🔶 |
| 锁课弹窗 | `.video-study>.dialog`（含 `.mask`） | 实测 | 弹窗可见 | ✅ |

## 附录 C：Track B 实测时间线（供回溯）

1. 密码登录 → 易盾滑块（4 次尝试：像素定位缺口 + 3 种轨迹均被环境检测拒绝）。
2. 扫码登录成功 → 课程列表 DOM → 进入共享课学习页（URL 密文破译验证）。
3. 章节树 / 播放器控件 / 倍速菜单选择器实测归档。
4. 学习页注入网络监听 + evaluate 播放 → 被踢出 → 重进后**课程锁定**（弹窗 + 异常记录页证据）。
5. 停止对该账号的一切自动化操作（避免其余课程被锁）；后续 M2 实测改用**有头 Chrome**（与生产同路径）并在锁定解除/换课后再进行。
