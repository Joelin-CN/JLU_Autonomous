# 验证清单 - 余额查询修复（2026-08-07）

## P0（必须）

- [x] `python -m pytest tests/unit/test_billing.py -q -s` 通过（15 passed，含新增 GBK 用例）
- [x] `npm run typecheck`（frontend/，两遍 vue-tsc）通过
- [x] 缺凭证场景复现：`python -m chaoxing.balance` 输出单行 ERROR JSON、exit 1，错误指向
  `data/passwords/volc_billing.txt`
- [x] 凭证路径解析正确：`CREDS_DIR = F:\Web\Chaoxing_auto\data\passwords`
- [x] 环境变量 pinning 正确：`CHAOXING_WORKSPACE`/`CHAOXING_DATA_DIR` 与 handler 一致
- [ ] 用户放置 `data/passwords/volc_billing.txt`（真实 AK/SK）后，卡片显示真实余额
  （需要用户提供凭证，代码侧无法代做）

## P1（重要）

- [x] 余额卡片失败时显示截断的短文案，悬停 `title` 与 DevTools 控制台含完整原因
- [x] 点击余额卡片可触发重新查询（`loadBalance`）
- [x] 解释器解析顺序：env 覆盖 > settings.pythonPath > python；失效绝对路径自动跳过并告警
- [x] 凭证文件支持 UTF-8 与 GBK 编码
- [x] `docs/design/api.md` §4.7 与实现一致

## P2（可选）

- [ ] 系统设置页补充 Python 路径入口（当前无 UI，只能靠 env 或删除 settings.json）
- [ ] 修复后端全量单测 5 个预存失败（`test_constants` 2 + `test_discover` 3，与本修复无关）
- [ ] 真实 AK/SK 联调后核对 `availableBalance` / `cashBalance` 字段与火山引擎账单页一致
