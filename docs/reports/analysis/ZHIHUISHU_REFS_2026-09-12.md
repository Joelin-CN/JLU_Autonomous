# 智慧树支持 · M0-A 参考矩阵（Track A 现有实现扫描）

> **状态：✅ 已完成**（2026-09-12）。本文为路线图 M0-A 产出物：四大来源（GitHub / GreasyFork / Userscript.Zone / OpenUserJS）现有实现扫描结论。
>
> 调研纪律：参考逻辑 ≠ 复制代码。许可证不明 / 无许可证项目只提炼思路；`references/`（git 忽略）存放脚本本体；MIT 且兼容的项目可按许可证注明来源后引用。**本文档中的安装量 / 时间 / 许可证以调研当日页面为准。**

---

## 1. GitHub 项目矩阵

| 项目 | 技术路线 | 最后更新 | 许可证 | 能力覆盖 | 现状判断 | 关键借鉴点 |
| --- | --- | --- | --- | --- | --- | --- |
| [CXRunfree/Autovisor](https://github.com/CXRunfree/Autovisor) | **Python + 异步 Playwright（真实 Edge/Chrome + stealth.min.js）** | 2026-09-07（v3.17.3，855★） | MIT | 登录（密码/手动兜底）、视频自动完成、倍速（UI 限 0.5–1.8）、弹题**跳过**（不答题）、进度识别 | ✅ 活跃，**浏览器路线标杆** | ①`add_init_script` 注入 stealth；②Yidun 滑块 OpenCV 模板匹配 + 随机分段轨迹（`modules/slider.py`）；③cookie 持久化 `data/cookies.json`；④选择器全套（见 §3）；⑤隐藏窗口时进度停滞的坑 |
| [VermiIIi0n/fuckZHS](https://github.com/VermiIIi0n/fuckZHS) | **接口直连（requests，无浏览器）** | 2025-10-28（2,249★） | MIT | 扫码登录（密码登录已被验证码卡死）、hike 校内学分课 + 知到共享课 + AI 课、视频倍速、弹题自动答（答案服务端泄露）、考试接口存在 | ⚠️ 部分可用 | ①两套 API 家族全量端点与签名（hike MD5 salt `o6xpt3b#Qy$Z`；知到 AES-128-CBC `secretStr` + XOR-hex `ev` key `zzpttjd`/`zhihuishu`）；②心跳节奏（watchPoint 1.99s / 进度 4.99s / `saveDatabaseIntervalTimeV2` 30s）；③完成阈值 0.91；④弹题 `lessonPopoupExam` 返回 `opt.result=='1'` 正确答案泄露 |
| [notnotype/zhihuishu-cli](https://github.com/notnotype/zhihuishu-cli) | 接口直连 CLI | 2023-11-28（24★，README 自称年久失修并指向 fuckZHS） | 无 | 扫码登录（WSS 轮询）、课程/章节/小节列表、学习进度心跳、视频 URL 解析 | ❌ 域名已迁移失效 | **协议路线可行性证明**：扫码 `passport.zhihuishu.com/qrCodeLogin/getLoginQrImg` + WSS `appcomm-user.zhihuishu.com`；心跳定时器镜像前端 1990/4990/18e4/3e5ms |
| [ymylive/zhihuishu_LOL](https://github.com/ymylive/zhihuishu_LOL) | 接口直连（fuckZHS 衍生） | 2025-11-27 | MIT | 扫码、弹题、AI 课、倍速标志 | ⚠️ 随 fuckZHS | 薄封装，无增量信息 |
| [luoyily/zhihuishu-tool](https://github.com/luoyily/zhihuishu-tool) | 接口直连 | 2022-11 停更（46★） | GPL-3.0 | 弹题自动答（`opt` 泄露）、成功信号 `{'code':0,'submitSuccess':True}` | ❌ 停更 | 弹题答案泄露的独立佐证 |
| [Cooanyh/zhihuishu-zhangwodu](https://github.com/Cooanyh/zhihuishu-zhangwodu) | **油猴/ScriptCat 纯 DOM + AI** | **2026-09-01**（18★） | **CC BY-NC-SA 4.0（NC！只借鉴思路不搬码）** | 掌握度答题（`.item-box.gray/.pink` 知识点 → AI 作答 / 题库 Levenshtein 90% 匹配）、单选/多选/判断/填空、自动翻页提交 | ✅ 活跃 | ①新学习域 `studywisdomh5.zhihuishu.com` / `wisdom-mooc.zhihuishu.com` 的答题选择器；②`reliableClick()` 用 `unsafeWindow` 派发 MouseEvent 让事件源自页面；③200ms 拟人延迟、AI 作答后 2s 限速 |
| [Looong01/Zhihuishu-Automatic-Answering](https://github.com/Looong01/Zhihuishu-Automatic-Answering) | 油猴 | 2023-03 归档 | MIT | 视频 + 考试/作业（答案来自第三方微信公众号 token 服务） | ❌ 死 | 无（token 依赖已失效） |
| [RManLuo/zhihuishu-auto](https://github.com/RManLuo/zhihuishu-auto) | Selenium | 2018-03 | 无 | 1.5x 静音播放 | ❌ 死 | 历史对照 |
| [Mr-xn/zhihuishu](https://github.com/Mr-xn/zhihuishu) | Chrome 扩展 | 2018-03 | 无 | 1.5x 自动播放 | ❌ 死 | 历史对照 |
| [ocsjs/ocsjs](https://github.com/ocsjs/ocsjs) | **多平台油猴（超星/智慧树/职教云/中国大学MOOC）** | 2026-07-01（3,386★） | MIT | 视频、答题（题库+AI 注入 DOM） | ✅ 活跃 | 多平台架构参考；issue #177 记录「检测到异常脚本」踢出文案与行为 |
| [666cy666/Script-Zhihuishu](https://github.com/666cy666/Script-Zhihuishu) | PyWebview+Vue+Selenium 桌面 | 2024-10-08 | BSD-2 | OCR + TF-IDF 匹配第三方题库 | ⚠️ | 桌面应用路线比油猴更难被检测的观点佐证 |
| [z5882852/zhihuishu-script](https://github.com/z5882852/zhihuishu-script) | 打包 exe | 2025-02 归档 | 无 | — | ❌ | 无 |

## 2. GreasyFork 脚本矩阵

| 脚本 | 更新 | 安装量 | 许可证 | 覆盖 | 现状 |
| --- | --- | --- | --- | --- | --- |
| [406653 知到智慧树刷课 v1.3.4](https://greasyfork.org/zh-CN/scripts/406653) | 2020-07 | ~11.7 万 | GPL-3.0 | 静音、1.25x、弹题「试选后 `.answer span` 暴露答案」、91% 阈值自动下一集、`.v-modal` 移除 | 选择器词汇仍有效（2026-09 实测），脚本本体过时 |
| [558335 智慧树全自动刷课 v3.1](https://greasyfork.org/zh-CN/scripts/558335) | 2025-12-08 | 197 | MIT | 自动播放（静音过自动播放策略）、`video.ended` 自动下一集、防暂停保活循环 | 自称 2025-12 可用，未验证 |
| [416950 刷课+作业](https://greasyfork.org/en/scripts/416950) | 2020-11 | 1.3 万 | 无（禁传播） | 作业页选择器、弹题点两项关闭 | 依赖第三方答题服务器（安全红线，不可用） |
| [422876 aecra 刷课 v0.2](https://greasyfork.org/en/scripts/422876) | 2021-07 | 5,818 | 无 | 1.5x、流畅画质、自动下一节 | 过时 |

## 3. 收敛后的选择器词汇表（多项目交叉 + 2026-09-12 本地实测）

**实测确认仍有效**（详见 `ZHIHUISHU_ANALYSIS_2026-09-12.md` 附录）：

- 播放器：`video`（video.js `#vjs_container`，`.vjs-tech`）；播放 `.bigPlayButton.pointer`；下一节 `#nextBtn`/`.nextButton`；进度 `.progressBar > .passTime`；时间 `.currentTime`/`.duration`；控制条 `.controlsBar`
- 倍速：`.speedBox > span`（当前值）+ `.speedList > .speedTab[rate=1.0|1.25|1.5]`（本课程上限 1.5）
- 音量：`.volumeBox`、`.volumeIcon`、`.passVolume`（高度百分比）
- 章节树：`ul.list > li.chapter`（`span.catalogue_title3 > b` 章号 + `span.catalogue_title` 章名）；`li.video`（+`.current_play` 当前节，`b.pl5.hour` 节号、`span.catalogue_title[title]` 标题）；`li.chapter-test[title=点击测试]`（章测入口）
- 弹题：`.el-dialog__wrapper.dialog-test`（旧）/`.el-dialog`（新）+ `.topic-item`；答案揭示 `.answer span`
- 完成标记：`.time_icofinish` / `.icon-finish` / `.progress-num == "100%"`；进度条 `.passTime` 宽度（切换阈值 91%）

## 4. 风险情报（Track A 汇总）

1. 「检测到异常脚本，为保证您的正常学习进度，请您关闭插件后，回到学堂重新进入视频学习页正常学习」→ 强制踢回首页（ocsjs #177；本地 2026-09-12 实测复现）。
2. **异常学习行为 → 课程锁定**（本地 2026-09-12 实测触发；异常记录四类：视频学习/见面课/考试/验证异常；申诉入口 `onlineh5.zhihuishu.com/subPage.html#/student/exceptionRecordList`）。
3. 播放器 JS 反调试：`debugger` 冻结、`fn.toString()` 完整性自校验、`console` 置空、控制流扁平化 + 字符串加密（避免 CDP 深度调试在线播放器）。
4. 行为信号：倍速异常有风险（服务端接受 >1x 但可暴露账号）、0.91 阈值（100% 精确重看会触发）、后台/最小化标签页节流导致进度停滞。
5. 自动播放策略：必须先 `video.muted = true`。
6. 登录：密码登录（Web + API）均被易盾滑块把守；异地登录触发短信验证。

## 5. 结论：路线组合

- **主路线 = Autovisor 模式**（真实 Chrome + 持久化 + stealth + 真实事件），其选择器与滑块方案直接对标我们的 playwright-cli 基础设施。
- **答题 = 406653 答案揭示技巧 + Cooanyh 新页选择器 + 自有 AI 路由**。
- **接口知识（fuckZHS）作后备**：不进 M2 主线；`recruitAndCourseId` 编码（本文首次本地验证）已用于 URL 构造。
