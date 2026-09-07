# 验证清单 — daemon 卡死自愈与一键扫描核查（2026-08-26 晚）

修复 08-26 全流程验证留下的两个待办：playwright-cli daemon 运行中 wedge、
UI 一键扫描偶发秒退。

## 一、daemon wedge 自愈链（P1-2，已修）

### 根因与死亡形态实测（三类，均实证）
| 形态 | 触发 | 表现 |
|---|---|---|
| TimeoutExpired | daemon 长空闲后卡死 | run-code/snapshot 超时（20/15/30s） |
| stdout `### Error: Target closed`（**rc=0**） | Chrome 刚死、daemon 未注销会话 | 错误在 stdout，rc 为 0 |
| stderr 堆栈 `Browser '...' is not open`（rc=1） | daemon 已注销会话 | CLI 客户端本地报错 |

此前代码只把 rc≠0+stderr 当错误——后两类完全漏检，第一类直接向上抛成
课程 FAILED（19:30 轮根因）。

### 修复（backend/chaoxing/browser/engine.py + 两 solver）
1. **pw() 三级恢复**：失败（超时或 SessionDeadError）→ 重试一次 →
   仍失败则 `_rebuild_session`（close → 清孤儿 Chrome → 重开 persistent
   profile → `_wait_session_ready` 就绪探测）→ 第三次尝试。
2. **死亡检测**：stderr + stdout 双流、rc=0/1 双形态、5 个 marker
   （closed/disconnected/target closed/is not open. run）。
3. **就绪探测**：rebuild 后轮询轻量 run-code（上限 25s）——`open` 在
   Chrome 启动完成前就返回，直接重试会把命令超时耗在浏览器启动上
   （22:14 前的实机教训）。
4. **课程上下文恢复**：rebuild 落在 about:blank，quiz/content 的章节树
   导航必失败 → 两 solver 在导航失败时 `open_course()`/`open_course_chapters()`
   重进课程页再试一次。
5. 恢复动作全部 `log()` 落盘（此前 print 到 stderr 不可排查）。

### 端到端验证（实机，杀 Chrome 模拟死亡）
- 修复前：杀 Chrome → 11 个 quiz 连环 Failed（Solved 0）。
- 修复后：杀 Chrome → 日志出现
  `SessionDeadError — retrying` → `rebuilding` → `rebuilt and ready` →
  导航失败自动 `re-entering course page` → **该测验 30 题完整解答并
  GRADE PASSED 100%（30✓/0✗）**，任务继续推进后续 quiz。
- UI 一键扫描（22:11 轮）：扫描中 SessionDeadError 两次瞬时重试直接
  恢复 → 扫完 11 门（1 门已完成剔除）保存 10 门 → 横幅「执行完成」。
- 单测：恢复链 3 类形态 + 就绪探测 + 普通错误不误触发，共 +9 用例。

## 二、UI 一键扫描秒退（P2，核查 + 加固）

洁净环境三次复现：任务均真实启动（Mode: scan_only / filter: none，
日志与文件写入齐全），**秒退未复现**。上次现象维持「疑似当时 pytest
并发写日志干扰，非稳定缺陷」。

加固（防复发可定位）：`execution.store.startJob` 同步失败（坏解释器/
内存预算/重复启动）此前只翻横幅、无留痕——现在同时写入日志控制台
「任务启动失败：<中文原因>」（invoke 包装前缀剥离）。若再发生，
日志控制台会留下定位线索。

## 三、验证汇总

- [x] 后端单测 **610 passed**（+9 恢复链用例，累计）；前端 typecheck 通过
- [x] 端到端：杀 Chrome 自愈（quiz 恢复 PASSED 100%）/ 扫描中途 SessionDead
  瞬时恢复并完成 / 停止后 chrome 清理无回归
- [x] UI 扫描 ×3：启动正常、数据写入正常、终态正确
- [x] 普通命令错误（rc≠0 非 death marker）不触发重建（回归用例）

## 已知边界（记录）

- rebuild 后页面语义依赖 solver 重进课程；若未来新增依赖页面状态的
  命令路径，需同样加「导航失败→重进」处理。
- daemon 对并发第二客户端报 not open（如外部 `playwright-cli list` 在
  任务运行时）为 CLI 固有行为，不在本次范围。
