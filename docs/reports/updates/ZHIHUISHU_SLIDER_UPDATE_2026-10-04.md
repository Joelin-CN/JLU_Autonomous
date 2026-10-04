# ZHIHUISHU_SLIDER_UPDATE_2026-10-04 — 易盾滑块自动求解落地（账密登录全自动）

- **类型**: 功能落地报告（D3「后备专项」经用户授权提前实施）
- **输入**: `ZHIHUISHU_SLIDER_ANALYSIS_2026-09-13.md`（专项结论与可行路径 A）、
  Autovisor（MIT，CXRunfree/Autovisor）公开实现思路
- **结论先行**: **账密登录 + 易盾滑块全自动求解真机验证通过——1 次尝试、
  零人工介入、`ensure_logged_in` 返回 True**。降级链变为：
  storageState → 扫码 → **密码 + 滑块自动求解** → 人工工单（兜底不删）。

---

## 1. 交付物

| 件 | 说明 |
|----|------|
| `backend/platforms/zhihuishu/slider.py` | 求解主模块：stealth 注入 / PNG 解码 / 缺口定位 / 拟人轨迹 / 闭环拖拽 / 编排 |
| `backend/scripts/stealth.min.js` | 完整版 stealth（berstend/puppeteer-extra MIT 构建产物，经 Autovisor 分发；137KB） |
| `backend/platforms/zhihuishu/auth.py` | 密码登录接自动求解优先；`ZHIHUISHU_LOGIN_MODE=auto|qr|password` |
| `backend/chaoxing_config.example.json` | `zhihuishu_slider: {auto_solve, max_attempts}` |
| `frontend/electron-builder.yml` | extraResources 白名单补 `scripts/stealth.min.js` |
| `backend/tests/platforms/zhihuishu/test_zhihuishu_slider.py` | 单测 24 个（PNG/定位/轨迹/资产守卫） |

开关：env `ZHIHUISHU_SLIDER_AUTO=0` 总关 / `ZHIHUISHU_SLIDER_ATTEMPTS=N` 次数
覆盖；配置 `zhihuishu_slider.auto_solve=false` 关闭；失败自动回退人工工单。

## 2. 技术方案（三级演进，全部真机数据驱动）

### 2.1 stealth 指纹补丁——验证了 M0「指纹拒绝」结论

- 内置 mini 补丁（webdriver=false / window.chrome 桩 / permissions 一致性）
  在闭环拖拽把落点做到 **±1.1px** 时仍被拒（2026-10-04 16:04 实测）——
  位置已非瓶颈，环境指纹仍是，与 M0 判断吻合。
- 换完整版 `stealth.min.js`（navigator/webgl/chrome/iframe 等十余模块）后
  通过。注入通道：`page.addInitScript`（后续导航）+ `page.addScriptTag`
  （当前页；语句序列不能走 evaluate 的表达式语义）。文件缺失自动降级
  mini 版（日志 WARN + 通过率下降），存在性有单测守卫。

### 2.2 缺口定位——边缘簇 → SAD 模板 → 命中率模板

真机（易盾 2.28.5 小尺寸弹窗，背景 element 截图 501×251 @DPR1.25）三级演进：

1. **暗带法** 失败：缺口内部仅比背景暗 7–13（背景照片偏亮，median 160）。
2. **边缘簇配对**（左右缘间距 35–95 CSS）：能出结果但置信度仅 ~0.3，
   易配到内容纹理（真图上内容边缘峰值与缺口缘同量级）。
3. **拼图轮廓命中率扫描（终版）**：取拼图 PNG 的 alpha 轮廓环样本
   （内部纹理与暗化缺口不匹配，只采轮廓），在背景二值边缘图
   （|∇|>40，±1px 容差）上沿 x 扫整圈命中率。拼图只水平滑动 → 单行扫描，
   纯 Python 亚秒。真机三对样本峰值 0.99/0.88/0.81 vs 远处次高
   0.60，配 `峰值≥0.45 且 远峰≤80%峰值` 门槛。**E2E 实战置信度 0.74–1.00。**

排除区：初始拼图块可见右缘（按 alpha bbox 折算到截图像素）+6px，
加最左 4px 截图边框伪影剔除。拼图 src 为 http 时走页内 fetch 取字节。

### 2.3 位移模型——真机标定出 k≈0.88 并闭环校正

- **标定实验**（按住拖 150px 不放测拼图位移）：拼图实际位移 **132px，
  k=0.88**——滑钮位移≠拼图位移，1:1 假设会系统性欠冲 ~12%（dx=220 时
  落点短 26px，必拒）。这解释了「±2px 误差仍被拒」阶段的真因。
- **闭环拖拽**：主轨迹按 1/0.9 估计行程 → 按住不放读拼图 boundingBox
  实际左缘 → `err/k` 迭代校正（≤3 轮，|err|≤1.2px 收敛）→ 释放。对 k
  的站点/窗口差异自适应；中途停顿/校正移动本身也是人类特征。
- 轨迹（Python 纯函数）：分段随机步长 + 中途迟疑 + 过冲回正 + 释放前
  微颤；总时长 0.4–1.6s；CDP `page.mouse` 真实事件（isTrusted）。

### 2.4 判定与重试

- 结果轮询 8s：`NECaptchaValidate` 填充 / tip 含「成功」/ **页面跳转离开
  login 域** 任一即成功；模态仍在 + 背景 src 刷新 = 落点被拒（提前重试）。
  ——修复判定竞态：真机曾出现 err1=-0.1px 已过、但 validate/跳转信号晚于
  一次性检查 2.5s 到达，被误判失败靠人工兜底路径捞回。
- 连续失败弹窗被易盾收起时，重按登录按钮重触发（登录成功导致的按钮
  消失则由「跳转即成功」信号接管）。

## 3. E2E 顺带抓修的 3 个存量缺陷

1. **密码兜底链一直 FORM_NOT_FOUND**：登录中心默认停「扫码」Tab；且
   「账号登录」Tab 的 Element Plus id 为 `tab-1.1`——`#tab-1.1` 被 CSS
   解析为 id+class 点空（扫码 Tab 恰好是 `#tab-3` 无点号所以历史正常）。
   修复：`_open_tab_by_text_real_click` 统一按文本找 Tab + `[id="..."]`
   属性选择器真实点击；密码登录前先切「账号登录」。
2. **复用已开会话不设 active session**：`ensure_zhihuishu_browser` 复用
   分支直接 return，后续 run-code 全打到默认 chaoxing 会话。修复：复用
   分支也 `set_active_session`。
3. **拖拽 JS 单行拼接中的 `//` 注释吞掉尾部**（排查脚手架期间引入）：
   playwright-cli 语法错误 `Unexpected end of input`；改 `/* */`。

## 4. 真机验证记录

### 4.1 最终 E2E（干净登录态，2026-10-04 16:17）

前提：清 profile Cookies + storageState；`ZHIHUISHU_HEADED=1
ZHIHUISHU_LOGIN_MODE=password python -c "ensure_logged_in(0)"`。

```
16:18:08 [slider] 第 1/3 次尝试
16:18:11 [slider] 缺口定位[模板匹配] x=154px（置信度 1.00）
16:18:17 [slider] 闭环校正：err0=4.9; err1=-0.1   ← 亚像素收敛
16:18:17 [slider] ✔ 验证通过（页面已跳转 zhihuishu.com）
16:18:32 登录态导出（70 cookies）→ E2E_LOGIN_RESULT: True
```

**1 次尝试通过，无人工工单**。全程 ~50s（含开浏览器/导航/表单）。

### 4.2 关键中间证据链

- k 标定：handler 150px → piece 132px（k=0.88）；
- 命中率曲线（真实样本）：x=282 rate=0.81，远峰 0.60；
- mini stealth + err1=1.1px 被拒 → 完整 stealth 后同样精度通过；
- 判定竞态实证：16:04 轮 err1=-0.1「误报失败」但登录实际完成（下一轮
  goto 直接跳首页确认）。

## 5. 已知边界与运维

- stealth 与易盾是持续军备竞赛：若通过率骤降，先查
  `ZHIHUISHU_SLIDER_DEBUG=1` 留存的 bg/piece 样本与置信度日志，
  重评 stealth 版本（上游 extract-stealth-evasions 更新构建）。
- 无头模式未验证通过路径；生产建议维持 `ZHIHUISHU_HEADED=1`
  （D3 原始约束：有头真实 Chrome）。
- 连续失败默认 3 次即回退人工工单（账号风控保守策略，勿盲目调大）。
- 调试脚手架（DOM 探测/标定/离线分析）：`data/temp/probe_zhs_slider.py`
  （git 忽略，不入库）。

## 6. 关联文档

- 可行性专项（前置结论）：`docs/reports/analysis/ZHIHUISHU_SLIDER_ANALYSIS_2026-09-13.md`
- 路线图 D3 实施记录：`docs/roadmap/zhihuishu.md` §8
- 验证清单：`docs/validation/VALIDATION_AFTER_SLIDER_AUTO_2026-10-04.md`

---

**文档版本**: 1.0　**创建**: 2026-10-04
