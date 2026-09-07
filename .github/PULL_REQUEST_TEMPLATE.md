<!-- 关联的 Issue（需求类必填）：Closes #N / Refs #N -->

## 变更说明

<!-- 做了什么、为什么。一两段话说清动机与方案。 -->

## 自验结果

<!-- 本地验证过的项目，附命令与结果摘要：
- 后端：python -m pytest tests/unit -q -s（backend/ 下）
- 前端：npm run typecheck && npm test（frontend/ 下）
- 其他手工验证（截图 / 日志，注意脱敏）
-->

## 影响面与文档同步

- [ ] 不影响 API 契约 / 架构；若影响，已同步 `docs/design/api.md`（或 architecture.md）
- [ ] 不含凭据、真实账号、未脱敏日志（见 docs/standards/secrets.md）
- [ ] 若涉及用户可见行为 / 配置，已同步对应 README
- [ ] 若为重要修复，已补 `docs/reports/fixes/` 报告与 CHANGELOG 条目

## 风险与回滚

<!-- 合并后可能出问题的点与回滚方式；无风险可写「无」 -->
