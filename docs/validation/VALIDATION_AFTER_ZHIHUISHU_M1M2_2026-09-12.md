# 验证清单：智慧树 M1+M2（平台抽象重构 + 登录/扫描）

> 事件：Zhihuishu M1（core/platforms 重构）+ M2（登录态 + 课程/章节扫描）+ 前端 IPC 平台化
> 日期：2026-09-12　分支：`feature/zhihuishu-m1-m2`（提交 124ed32 / ceda03d / 4e07517）

## P0（必须）

| # | 项目 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | 超星后端单测全量回归 | ✅ | `python -m pytest tests/unit -q -s` → **618 passed 零失败**（重构后）；智慧树包加入后全仓 **629 passed** |
| 2 | 旧入口兼容（`python -m chaoxing.*`） | ✅ | `--help` / `accounts list` 冒烟通过；`chaoxing.api is platforms.chaoxing.api` 模块同一性断言通过（monkeypatch 语义不变） |
| 3 | XOR 编码器实测向量 | ✅ | `("428215","1000003834") → 4e5a…405c`（单测固定向量，源自实地抓取 URL） |
| 4 | 智慧树扫码登录（有头 Chrome） | ✅ | scan6 实测：TICKET 二维码工单 → 用户知到 APP 扫码 → 跳转检测（95s 全链路） |
| 5 | 智慧树课程+章节扫描 | ✅ | scan6：1 门共享课识别（翻转课正确跳过）、章节树解析、`discovered_courses_zhihuishu-chrome-0.json` 落盘、`courses --account 0` 输出正常 |
| 6 | 前端 typecheck | ✅ | `npm run typecheck` 全绿（Platform 类型 + 5 处 spawn 位平台化后） |
| 7 | 打包白名单覆盖新布局 | ✅（静态核验） | electron-builder.yml 含 `core/**`、`platforms/{chaoxing,zhihuishu}/**`、`chaoxing/**` 垫片；backendPath marker 指向 `platforms/chaoxing/api.py`（P2 补实包验证） |

## P1（重要）

| # | 项目 | 结果 | 说明 |
| --- | --- | --- | --- |
| 8 | 滑块人工工单兜底链路 | ✅（机制就位） | 密码登录→易盾滑块→截图工单→人工在窗口拖拽→轮询跳转；自动求解为独立专项 |
| 9 | 超星 Electron 端到端冒烟 | ⏳ 待验 | 行为零改动（纯移动+参数化），typecheck 过；建议合并前手动跑一次扫描任务 |
| 10 | 双平台并发 / RAM 治理 | ⏳ M2 后 | zhihuishu api 单账号串行；并发化在 M3 编排接入时验证 |

## P2（可选）

- 打包产物实机安装验证（extraResources 种子正确性）
- zhihuishu.txt 增删改（accounts add/edit/remove）UI 链路（渲染层平台 UI PR）

## 已知限制（M3 待办）

1. **智慧树登录 Cookie 为会话级**：Chrome 重启后登录态丢失（与超星持久 profile 不同）→ 每任务需现场扫码；M3 评估 storageState 导出/恢复或首任务建态后续复用。
2. **章节树懒加载**：`ul.list` 在 el-scrollbar 中仅渲染可视区（scan6 实测锁定课只见 1 章/3 节）→ M3 加滚动加载再解析。
3. 课程锁定弹窗（异常学习行为）会遮挡章节树 → scanner 已先点「下次再说」，锁定课本身跳过处理（M3 加显式检测与跳过日志）。
4. 渲染层平台切换 UI 未交付（IPC 已就绪，默认平台行为不变）。

---

## M3 增补实测（2026-09-12 晚，feature/zhihuishu-m3）

| # | 项目 | 结果 | 证据 |
| --- | --- | --- | --- |
| M3-1 | storageState 零扫码闭环 | ✅ | 第 2 轮任务免扫码（75 cookies 恢复→直接登录，34s vs 首轮扫码 105s） |
| M3-2 | 章节树滚动加载 | ✅ | 懒加载补全 38 节点（26 视频 + 章测），此前仅可视区 3 节点 |
| M3-3 | 学前必读弹窗处理 | ✅ | DOM+视觉双确认：无确认按钮，关闭=右上角 X（.dialog-read .iconguanbi），带重试 |
| M3-4 | 课程提醒弹窗清扫 | ✅ | watch-loop 每轮检测自动点「下次再说」（播放中途会再弹，实测 ×3） |
| M3-5 | 弹题自动作答 | ✅ | 试选→.answer 揭示「正确答案：B」→选 B→关闭→进度入账（进度条 27.6%→33.8%），全程真实点击 |
| M3-6 | 原速真实播放（D6） | ✅ | rate=1.0 全程；播放启动=点击 .videoArea（.bigPlayButton 需 hover 且悬停态跨命令不保持） |
| M3-7 | 单节完整完成 | ✅ | 0.1 节 456/456s（DOM .time_icofinish 标记 + 视觉 07:36/07:36 片尾画面），途中自动处理 2 弹题 + 2 课程提醒 |

D6 红线执行情况：全程真实点击（播放/静音/选项/关闭/X）、观察 JS 只读、零心跳伪造、1.0 倍速。
已知后续项：fixed 定位元素的可见性判定已统一 rect+computedStyle（offsetParent 对 fixed 恒 null，三处弹窗检测曾因此漏检）。
