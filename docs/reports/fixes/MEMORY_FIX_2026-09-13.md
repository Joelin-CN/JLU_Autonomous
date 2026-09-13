# MEMORY_FIX_2026-09-13 — Chrome 内存采样性能专项（CIM 查询 >20s）

- **类型**: 性能修复（P1-3）
- **影响面**: `backend/core/memory.py`（`measure_project_chrome_gb`）、`frontend/electron/memory/planner.ts`（`measureProjectChromeGB` 镜像）、`backend/tests/unit/test_memory.py`
- **门禁**: 后端 `pytest tests/unit -q -s` = 626 passed（621 基线 + 5 新增）；前端 `npm run typecheck` = 0 错误

## 问题发现

2026-09-13 真机双平台联测与日常运行中观察到：多 Chrome 进程时
`measure_project_chrome_gb` 的 PowerShell CIM 查询耗时超过 20s，
触发 `subprocess.TimeoutExpired`。此前已有降级兜底（监视线程不死、
该轮跳过，见 `e889ac17`），但采样变慢本身未解决——表现为 MEMORY 事件
稀疏、内存闸门（orchestrator gate）等待期间轮询迟滞。

## 根因

每次采样都新起一个 `powershell.exe` 进程执行：

```powershell
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'"
```

两个成本来源：

1. **全量 CIM 查询**：`Win32_Process` 枚举全部进程再按 Name 过滤，且默认
   编组全部属性（CommandLine/WorkingSetSize 等）。Chrome 进程树动辄上百个
   进程、每个 CommandLine 数 KB，WMI 编组成本随之膨胀，冷启动 WMI 仓库时
   尤甚，可破 20s。
2. **零缓存的双路消费**：`MemoryMonitor` 线程（5s 周期）与 orchestrator
   内存闸门（账号线程等槽位时轮询）并发调用同一探针，同一秒内可能重复
   spawn powershell 重复支付查询成本。

## 方案

三层优化，语义零变化（返回值、失败行为、非 win32 抛错均不变）：

1. **粗筛快路径**：PS 脚本头部用 `Get-Process -Name chrome`（.NET 内核 API，
   毫秒级）确认 chrome 存在性；不存在则直接输出 `'0'` 并 `return`，完全
   跳过 CIM。空闲态/浏览器未起时的采样从 20s 级降到亚秒级。
2. **属性投影**：CIM 查询加 `-Property WorkingSetSize,CommandLine`，只编组
   后续真正用到的两个字段，降低有 chrome 时的查询成本。
3. **TTL 缓存**：模块级缓存按 `profile_root` 键控，TTL 2s（常量
   `MEASURE_CACHE_TTL_S`，线程安全锁）；去重 Monitor 与 gate 的并发查询。
   失败（任何异常）不写缓存；提供 `_clear_measure_cache()` 测试钩子。

前端 `planner.ts#measureProjectChromeGB`（job:start 基线测量用）镜像了
第 1、2 层——它的调用频率低（仅任务启动时），不值得引入缓存。

### 优化后脚本（backend）

```powershell
if (-not (Get-Process -Name chrome -ErrorAction SilentlyContinue))
  { [Console]::Out.Write('0'); return }
$p = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" `
    -Property WorkingSetSize,CommandLine
$m = $p | Where-Object { $_.CommandLine -like '*<root>*' }
$s = ($m | Measure-Object -Property WorkingSetSize -Sum).Sum
if ($null -eq $s) { $s = 0 }
[Console]::Out.Write([string]($s))
```

## 验证

- `tests/unit/test_memory.py` 新增 5 用例（照抄既有 monkeypatch
  `subprocess.run` 模式）：
  - 脚本含粗筛守卫且位于 CIM 之前、含属性投影（recorder 捕获脚本断言）；
  - TTL 内同 root 只 spawn 一次；
  - 缓存按 root 键控（双平台档案根不串值）；
  - TTL 过期重新 spawn（Monitor 5s 周期拿新值）；
  - 失败不缓存（首轮 rc=1 抛错后第二轮能拿到新值）。
- 受影响旧用例以 autouse fixture `_fresh_measure_cache` 隔离缓存。
- 有 chrome 运行时的实际收益（>20s → ?）依赖机器 WMI 状态，属性投影为
  尽力优化；无 chrome 场景的快路径收益确定（彻底跳过 CIM）。

## 遗留观察

- 若极端机器上带 chrome 的 CIM 仍超 20s，下一步候选：把两次探针
  （project + system）合并为单次 PS 调用，或改用 WMI 永久会话——当前
  不做，保持改动最小。
