# VALIDATION_AFTER_SLIDER_AUTO_2026-10-04 — 易盾滑块自动求解验证清单

> 关联：`docs/reports/updates/ZHIHUISHU_SLIDER_UPDATE_2026-10-04.md`（实施报告）
> 分支：`feature/parallel-platform-jobs`　验证环境：Windows / Py3.13 / 真机（有头 Chrome）

## P0（必须）

- [x] **P0-1 单元测试全绿**：`python -m pytest tests/unit tests/platforms -q -s`
  → **700 passed**（含滑块新增 24：PNG 解码 round-trip×5 / 缺口定位合成用例×4 /
  模板匹配×3 / alpha bbox×2 / 轨迹性质×5 / stealth 脚本×4 / 资产守卫×1）。
- [x] **P0-2 stealth 资产在库**：`backend/scripts/stealth.min.js`（137KB，MIT）存在
  且 `TestStealthAsset::test_full_stealth_shipped` 守卫通过（防打包/克隆遗漏静默降级）。
- [x] **P0-3 干净登录态全链路 E2E（2026-10-04 16:17）**：
  清 profile Cookies + storageState → `ZHIHUISHU_HEADED=1
  ZHIHUISHU_LOGIN_MODE=password` 跑 `ensure_logged_in(0)` →
  **1 次尝试通过、零人工工单**：定位置信度 1.00 → 闭环 err 4.9→-0.1px →
  页面跳转 www.zhihuishu.com → storageState 导出 70 cookies → True。

## P1（重要）

- [x] **P1-1 禁用开关回退路径**：`ZHIHUISHU_SLIDER_AUTO=0` / 配置关 →
  `auto_solve_slider` 直接 False，auth 走原人工工单流程（代码路径 +
  日志核验；工单文案已更新为「自动求解未通过，请手动拖动」）。
- [x] **P1-2 判定竞态修复**：validate/跳转信号晚于落点 2–5s 的形态由
  8s 轮询覆盖（16:04 轮曾误判失败、靠兜底路径捞回 → 16:17 轮修复后
  第 1 次尝试即正确返回成功）。
- [x] **P1-3 存量缺陷回归**：密码登录 Tab 切换（`[id="tab-1.1"]` 属性
  选择器）正常；`ensure_zhihuishu_browser` 复用会话设 active session
  （E2E 多轮开关浏览器验证）。
- [x] **P1-4 打包白名单**：`frontend/electron-builder.yml` extraResources
  含 `scripts/stealth.min.js`。

## P2（可选 / 后续观察）

- [ ] **P2-1 多账号并发登录**：account-1+ 的滑块求解尚未真机验证
  （单账号链路一致，风险低；下次多账号作业顺带观察）。
- [ ] **P2-2 无头模式通过率**：未验证；生产维持 `ZHIHUISHU_HEADED=1`
  （D3 约束）。
- [ ] **P2-3 长期通过率观察**：stealth×易盾军备竞赛——若通过率骤降，
  用 `ZHIHUISHU_SLIDER_DEBUG=1` 留样分析（data/temp/slider-bg-fail-*.png
  + slider-piece-*.png），重评上游 stealth 构建。
- [ ] **P2-4 重试次数调优**：默认 3 次（账号风控保守）；多账号高频
  登录场景可评估 4–5 次的通过率/风控平衡。

## 复验命令

```bash
# 后端（backend/ 下；Windows/Py3.13 需 -s）
python -m pytest tests/unit tests/platforms -q -s

# 全链路 E2E（干净登录态：先清 data/chrome-profiles/zhihuishu/account-0
# 的 Default/Network 与 Default/Cookies，删同目录 storage-state.json）
cd backend
ZHIHUISHU_HEADED=1 ZHIHUISHU_LOGIN_MODE=password python -c \
  "import sys; sys.path.insert(0,'.'); from platforms.zhihuishu.auth import ensure_logged_in; print(ensure_logged_in(0))"
```

---

**结论**: P0/P1 全过，P2 留观察项。滑块自动求解进入生产可用状态。
