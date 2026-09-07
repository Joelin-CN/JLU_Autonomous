# 安全策略

本仓库为公开仓库，请所有使用者与协作者遵守以下红线。

## 凭据红线

- 平台账号、密码、验证码、API Key、浏览器登录态**永不入库**，也**永不出现在 Issue / PR / 评论 / 截图 / 日志粘贴**中（详见 [docs/standards/secrets.md](docs/standards/secrets.md)）。
- 提交前扫描敏感模式：11 位手机号、`sk-` / `ark-` 开头的密钥串、真实 `chaoxing_config.json`。
- 发现泄露立即按 [docs/standards/secrets.md §4](docs/standards/secrets.md) 应急流程处置：先作废凭据，再清理历史。

## 漏洞报告

- 本项目依赖的凭据全部保存在使用者本机（`data/passwords/`，git 忽略），仓库本身不存储任何密钥。
- 发现安全问题请勿直接开公开 Issue，先私下联系维护者（[@Joelin-CN](https://github.com/Joelin-CN) / [@Arthur-Pendrag0n](https://github.com/Arthur-Pendrag0n)）；确认修复后再公开讨论。

## 使用边界

本项目仅供个人学习与技术研究（详见 [README](README.md) 声明）。使用者需自行承担违反平台条款的风险与后果。
