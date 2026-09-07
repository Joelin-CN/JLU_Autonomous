# 验证清单 — 账号 / CLI / 状态机修复批次

日期：2026-08-13

## P0（必须）

- [x] 双无下标账号块可正常解析，不再抛 `TypeError`（自动化用例）
- [x] `website[N]` 写读回环不丢自定义登录网址（自动化用例）
- [x] `python scripts/chaoxing_orchestrator.py --status` / `--help` 正常
- [x] `python tests/_test_phase_c.py --help` 导入链路正常
- [x] `chaoxing_cli.ps1` PowerShell 语法解析通过
- [x] 后端全量单元测试通过（584 pass）
- [x] 前端 `npm run typecheck` 通过

## P1（重要）

- [x] `api.py` 无凭证/无匹配账号时发 `ERROR + DONE + exit 1`（代码审查 + 单元测试）
- [x] `job.handler.ts` `done` 不再把 error 状态翻转为 completed（代码审查）
- [x] 旧 bridge 的 `exit`/`error` 不再清空新任务全局状态（代码审查）
- [x] Electron 默认 Python 路径不再包含盘符硬编码
- [x] 退出清理不再 `taskkill /im chromium.exe /t` 全局杀进程

## P2（可选）

- [x] 删除 `refreshAccountStatus` 死代码
- [x] 清理 Electron/共享类型中的 `deepseekModel` / `doubaoModel` / `autoResolve` 残留
- [x] 三份 README、api.md、integration.md、API_SPEC.md 与代码现状一致
- [x] architecture.md / API_REFERENCE.md / auto-solution-design.md 标注历史参考

## 待人工复核（需真实浏览器/账号环境）

- [ ] `chaoxing_cli.bat` 交互菜单完整跑一遍（scan / full-auto，P/Q 按键）
- [ ] Electron 端到端跑一次失败任务，确认不再弹“全部完成”且状态为 error
- [ ] 连续启动两个任务（前一任务退出后立即启动），确认无竞态
