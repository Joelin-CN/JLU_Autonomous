# 账号解析 / CLI / 状态机修复报告

日期：2026-08-13

## 问题发现

1. **P0 多账号凭证解析崩溃**：`read_all_chaoxing_credentials()` 把“账号字符串集合”
   当作索引集合使用，遇到第二个无 `[N]` 下标的账号块时执行
   `max(seen_indices) + 1`，字符串 + 整数抛 `TypeError`。已用真实解析器复现。
2. **P0 自定义登录网址丢失**：`accounts.py` 写 `website[N]: ...`，但
   `_parse_credential_block()` 只识别无下标的 `website`，增删改账号后自定义网址被静默
   丢弃并回落到默认登录页。已用真实解析器复现。
3. **P1 CLI 完全失效**：`scripts/chaoxing_orchestrator.py` import 已删除的
   `main` / `cmd_status` / `_parse_accounts_arg`；`utils.py` import 已删除的
   `ACCOUNT_SEMAPHORE`；`chapter_*` shim import 不存在的 `main`。实测两种启动方式均
   崩溃，连带 `chaoxing_cli.bat/ps1` 与 batch-test 失效。
4. **P1 失败任务显示为成功**：后端 `api.py` 失败路径先 `ERROR` 后 `DONE`，Electron
   `done` 回调无条件置 `completed` 并弹“全部完成”通知。
5. **P1 bridge 竞态**：旧任务残留 `exit`/`error` 事件无条件清空全局
   `bridge` / `activeJobId` / 活动标志，可能误伤紧接着启动的新任务。
6. **P2 路径与进程治理**：Electron 默认 Python 路径硬编码 `E:\Softwares\...`；
   退出时 `taskkill /im chromium.exe /t` 按进程名全局杀；`refreshAccountStatus`
   死代码会用空 username 覆盖账号数据。

## 修复方案

- `auth.py`：`used_indices` 独立为整数集合分配无下标账号序号；下标正则扩展支持
  `website[N]` / `网站[N]`。
- `scripts/`：`chaoxing_orchestrator.py` 重写为向后兼容入口（映射旧参数到
  `run_multi_account`，支持 `--status` / `--dry-run` / `--resume`）；
  `utils.py` 删除失效导入；`chapter_*` shim 改为弃用提示；`doubao_api.py` 补路径引导。
- `chaoxing_cli.ps1`：去掉硬编码 Python 路径；P/Q 改走 stdin 信号；batch-test 参数
  修正为 `--section`；修复“起始章节”提示缺少闭合引号导致的脚本语法错误。
- `orchestrator.py`：`run_multi_account` 新增 `dry_run` / `resume` 透传参数。
- `job.handler.ts`：`done` 在 `status === 'error'` 时不再翻转；新增
  `clearActiveJobIfCurrent` 守卫旧 bridge 事件。
- `api.py`：启动前预检凭证与账号索引，缺失时 `ERROR + DONE + exit 1`。
- `types.ts` / `main.ts` / `account.store.ts`：Python 默认路径置空、定向 Chromium
  清理、删除账号状态死代码、清理 DeepSeek 残留字段。

## 验证

- 新增单元测试：双无下标账号块解析、`website[N]` 解析、`add --website` 写读回环。
- `python -m pytest tests/unit/test_auth.py tests/unit/test_accounts_commands.py -q -s` 全绿。
- 受影响模块 107 个测试全绿；前端 `npm run typecheck` 通过。
- CLI 冒烟：`python scripts/chaoxing_orchestrator.py --status` / `--help`、
  `python tests/_test_phase_c.py --help` 均正常。
- 全量回归见 [验证清单](../../validation/VALIDATION_AFTER_FIX_BATCH_2026-08-13.md)。
