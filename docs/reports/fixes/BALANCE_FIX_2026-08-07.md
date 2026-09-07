# 余额查询修复报告 - 2026-08-07

## 一、现象（用户反馈）

前端 API 余额查询异常：Dashboard「💳 可用余额」卡片无法展示余额。

## 二、根因（证据链）

### 1. 直接根因：火山引擎账单凭证文件缺失

`data/passwords/volc_billing.txt` **不存在**（`data/passwords/` 下只有 `chaoxing.txt` /
`doubao.txt` / `pwd.txt`；旧路径 `backend/passwords/` 下也没有）。后端
`chaoxing/ai/billing.py::_load_billing_credentials()` 在文件缺失时抛 `ConfigError`，
CLI 输出 ERROR JSON、exit code 1，前端卡片因此显示「余额查询失败」。

实际复现（`chaoxing-backend` 环境，与 Electron handler 相同的 env pinning）：

```json
{"type":"ERROR","error":"Volcano billing credentials not found: F:\\Web\\Chaoxing_auto\\data\\passwords\\volc_billing.txt\nCreate data/passwords/volc_billing.txt with VOLC_ACCESS_KEY and VOLC_SECRET_KEY (see docs/design/api.md).","detail":"ConfigError"}
```

该文件需要用户手动放置火山引擎**账单 OpenAPI** 的 AK/SK（与 `doubao.txt` 的
`ARK_API_KEY` 是两套独立凭证，不可混用）。删除前的
`backend/.claude/plans/balance-query.plan.md` 也明确写明「待你提供
`passwords/volc_billing.txt` 里的 AK/SK（联调时需要）」。

### 2. 链路其余部分验证为可用

- 专用 conda 环境 `E:\Softwares\Anaconda\envs\chaoxing-backend`（Python 3.13.14）存在，
  `volcenginesdkcore` / `volcenginesdkbilling` 可正常导入。
- `frontend/electron/ipc/balance.handler.ts` → `python -m chaoxing.balance` →
  `ai/billing.py` 的 spawn / 30s 超时 / ERROR JSON 解析 / ENOENT 中文提示均实现且正确。
- 环境变量白名单、`CHAOXING_WORKSPACE` / `CHAOXING_DATA_DIR` pinning、凭证路径解析
  （`CREDS_DIR = DATA_ROOT / "passwords"`）均正确。

### 3. 次生问题（本次一并加固）

| 问题 | 影响 |
| --- | --- |
| `settings.json` 可能残留旧 `pythonPath`（如系统 Python），且系统设置页**没有** Python 路径入口（PATH_FIX 报告中的「系统设置改一次」说法不成立） | 余额查询可能用错解释器（SDK 缺失或 ENOENT） |
| 凭证文件仅按 UTF-8 读取 | 中文 Windows 记事本以 ANSI/GBK 保存时解析失败 |
| Dashboard 错误信息为后端原文（长、多行），且无重试入口 | 用户看不清原因、修完凭证后只能重启应用 |
| `types.ts` 注释声称可在「系统设置」覆盖 | 与事实不符，误导排查 |

## 三、修复方案

### 1. 凭证文件编码兼容（后端）

`billing.py` 新增 `_read_creds_file()`：按 UTF-8 → GBK 依次尝试解码；均失败时抛出带
明确提示的 `ConfigError`。

### 2. 解释器解析加固（前端 IPC）

`balance.handler.ts::getBalancePython()` 明确解析顺序并在主进程控制台记录所选解释器：

1. `CHAOXING_BALANCE_PYTHON` 环境变量（显式覆盖）；
2. `Settings.pythonPath`（默认已指向 `chaoxing-backend` 的 `python.exe`）；
   - 若配置的是**不存在的绝对路径**（陈旧 settings.json），自动跳过并告警；
3. `PATH` 上的 `python`。

### 3. Dashboard 余额卡片体验（渲染端）

- 错误信息截断为单行短文案（≤30 字符），完整原因放悬停 `title` 并在 DevTools 控制台输出；
- 卡片支持点击重试（`GlassmorphicCard :clickable`），创建凭证后无需重启应用。

### 4. 注释与文档同步

- `frontend/electron/types.ts`：纠正「系统设置可覆盖」的错误注释；
- `docs/design/api.md` §4.7：更新解释器解析顺序、凭证文件编码说明、卡片点击重试说明。

### 5. 测试

`tests/unit/test_billing.py` 新增 GBK 编码凭证文件解析用例。

## 四、验证结果

| 验证项 | 命令 | 结果 |
| --- | --- | --- |
| 余额单测 | `python -m pytest tests/unit/test_billing.py -q -s`（chaoxing-backend） | **15 passed**（含新增 GBK 用例） |
| 后端全量单测 | `python -m pytest tests/unit -q -s` | **553 passed / 5 failed**（5 个为预存失败：`test_constants` 2 个 + `test_discover` 3 个，与本次改动无关，见 PATH_FIX 基线） |
| 前端类型检查 | `npm run typecheck`（frontend/） | 通过（两遍 vue-tsc 均无错误） |
| 链路复现 | `python -m chaoxing.balance`（缺凭证场景） | 输出单行 ERROR JSON，exit 1（预期，待用户放置凭证后转为 BALANCE） |

## 五、涉及文件

### 后端
- `backend/chaoxing/ai/billing.py` — 凭证文件 UTF-8/GBK 兼容读取
- `backend/tests/unit/test_billing.py` — 新增 GBK 用例

### 前端
- `frontend/electron/ipc/balance.handler.ts` — 解释器解析加固 + 日志
- `frontend/src/views/DashboardView.vue` — 错误展示截断/悬停/点击重试
- `frontend/electron/types.ts` — 注释纠正

### 文档
- `docs/design/api.md` — §4.7 同步
- 本报告 + `docs/validation/VALIDATION_AFTER_BALANCE_FIX_2026-08-07.md`

## 六、遗留事项与用户操作（P0）

**要真正显示余额，用户需要创建 `data/passwords/volc_billing.txt`**（火山引擎账单
OpenAPI AK/SK，非豆包 ARK_API_KEY）：

```text
export VOLC_ACCESS_KEY="AK..."
export VOLC_SECRET_KEY="SK..."
region="cn-north-1"          # 可选，默认 cn-north-1
```

放置后点击 Dashboard 余额卡片即可重试，无需重启。

## 七、风险与建议（P1/P2）

- P1：系统设置页无 Python 路径入口；如 `%APPDATA%\超星助手\settings.json` 残留旧
  `pythonPath`，建议后续在设置页补充入口，或提示用户删除该文件 / 设置
  `CHAOXING_BALANCE_PYTHON`。
- P1：后端全量单测存在 5 个预存失败（`test_constants` / `test_discover`），不属于本
  问题域，建议另立任务修复。
- P2：`test_billing.py` 的 SDK 缺失用例依赖 `builtins.__import__` 拦截，可考虑改为
  `sys.modules` 占位以更贴近真实 lazy-import 行为。
