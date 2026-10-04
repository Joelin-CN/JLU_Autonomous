"""易盾（Yidun）滑块自动求解 —— 智慧树账密登录滑块专项实现。

背景（`docs/reports/analysis/ZHIHUISHU_SLIDER_ANALYSIS_2026-09-13.md`）：
M0 实测 4/4 被拒的根因是**环境指纹**（CDP webdriver 特征），缺口定位与
轨迹都不是瓶颈。可行路径 = 真实 Chrome（本工具链 `open --browser=chrome`
已满足）+ stealth 指纹补丁 + 拟人轨迹（Autovisor 验证过的组合）。

本模块四件事：
    1. ``inject_stealth``   反自动化指纹补丁（webdriver=false 等），
                            当前页 evaluate + 后续导航 addInitScript，幂等；
    2. 缺口定位            背景 element 截图 → 纯 stdlib PNG 解码 →
                            暗带 + 垂直边缘双通道检测；
    3. 拟人轨迹            Python 侧生成分段随机轨迹（含过冲回正），
                            ``page.mouse`` 按点回放（trusted 事件）；
    4. ``auto_solve_slider``编排：探测 → 定位 → 拖拽 → 校验，N 次重试。

开关（默认开，失败自动回退人工工单，见 auth.py）：
    ZHIHUISHU_SLIDER_AUTO=0          总开关（env）
    cfg("zhihuishu_slider.auto_solve")   配置文件同名开关
    cfg("zhihuishu_slider.max_attempts") 重试次数（默认 3）
    ZHIHUISHU_SLIDER_ATTEMPTS        重试次数 env 覆盖

工程红线不变：拖拽走 CDP 真实鼠标事件（isTrusted），禁止 evaluate
合成 pointer 事件（易盾校验事件流）。
"""

import base64
import json
import os
import random
import struct
import time
import zlib

from core.config import cfg
from core.constants import TMP_DIR, WORKSPACE
from core.logging_setup import log

from core.browser.js_runner import _run_js_file

# 易盾 v2 DOM（实弹探测校准；探测 JS 会在元素上打 data-zhs-* 标记，
# 后续截图/拖拽统一按标记取元素，避免类名变体漂移）。
# 元素标记：data-zhs-bg / data-zhs-jigsaw / data-zhs-handler / data-zhs-track

# ── 纯 stdlib PNG 解码 ────────────────────────────────────────────

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PngError(ValueError):
    """PNG 数据不受支持或损坏。"""


def decode_png(data: bytes):
    """极简 PNG 解码 → (width, height, rows)，rows[y] 为 RGBA 字节串。

    支持位深 8、彩色类型 0/2/3/4/6、非隔行、全部 5 种行过滤器——覆盖
    Chromium 截图与易盾拼图 PNG（stdlib zlib，无 Pillow 依赖，
    requirements.txt 保持纯标准库）。
    """
    if not data.startswith(_PNG_SIGNATURE):
        raise PngError("not a PNG file")
    pos = 8
    header = None
    idat = bytearray()
    palette = None
    trans = None
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        pos += 4
        ctype = data[pos:pos + 4]
        pos += 4
        chunk = data[pos:pos + length]
        pos += length + 4  # chunk + CRC
        if ctype == b"IHDR":
            w, h, depth, color, _comp, _filt, interlace = \
                struct.unpack(">IIBBBBB", chunk)
            if depth != 8:
                raise PngError(f"unsupported bit depth {depth}")
            if interlace != 0:
                raise PngError("interlaced PNG unsupported")
            header = (w, h, color)
        elif ctype == b"PLTE":
            palette = chunk
        elif ctype == b"tRNS":
            trans = chunk
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
    if header is None:
        raise PngError("missing IHDR")
    w, h, color = header
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    if channels is None:
        raise PngError(f"unsupported color type {color}")
    stride = w * channels
    raw = zlib.decompress(bytes(idat))
    if len(raw) < (stride + 1) * h:
        raise PngError("truncated pixel data")

    def _paeth(a: int, b: int, c: int) -> int:
        pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
        if pa <= pb and pa <= pc:
            return a
        return b if pb <= pc else c

    out = bytearray(stride * h)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        ftype = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if ftype == 1:  # Sub
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ftype == 2:  # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:  # Average
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:  # Paeth
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                line[i] = (line[i] + _paeth(a, b, c)) & 0xFF
        elif ftype != 0:
            raise PngError(f"bad filter type {ftype}")
        out[y * stride:(y + 1) * stride] = line
        prev = line

    rows = []
    for y in range(h):
        base = y * stride
        row = bytearray(w * 4)
        for x in range(w):
            o = x * 4
            if color == 6:
                row[o:o + 4] = out[base + x * 4:base + x * 4 + 4]
            elif color == 2:
                i = base + x * 3
                row[o:o + 3] = out[i:i + 3]
                row[o + 3] = 255
            elif color == 0:
                v = out[base + x]
                row[o:o + 3] = bytes((v, v, v))
                row[o + 3] = 255
            elif color == 4:
                i = base + x * 2
                v, a = out[i], out[i + 1]
                row[o:o + 3] = bytes((v, v, v))
                row[o + 3] = a
            else:  # 3: palette
                idx = out[base + x]
                if palette is None or idx * 3 + 2 >= len(palette):
                    raise PngError("bad palette index")
                row[o:o + 3] = palette[idx * 3:idx * 3 + 3]
                row[o + 3] = trans[idx] if (trans and idx < len(trans)) else 255
        rows.append(bytes(row))
    return w, h, rows


# ── 缺口定位（纯函数，单测覆盖）────────────────────────────────────

def _to_gray(rows, w, h):
    gray = []
    for row in rows:
        g = bytearray(w)
        for x in range(w):
            o = x * 4
            g[x] = (row[o] * 299 + row[o + 1] * 587 + row[o + 2] * 114) // 1000
        gray.append(g)
    return gray


def locate_gap_x(rows, w: int, h: int, exclude_until: int = 0, dpr: float = 1.0):
    """在背景图像素中定位缺口左缘 → (x | None, confidence)。

    实测校准（2026-10-04 真机：2.28.5 小尺寸弹窗，501×251 截图）：
    缺口只占图高 ~33%，左右缘是两条间距 ≈ 拼图可见宽度的强垂直边缘簇
    （列上 |Δ|>26 的行计数），内部仅比背景暗 7-13（暗带法失效）。
    故主通道 = **边缘簇配对**：找间距 35–95 CSS 的簇对，取左簇起点；
    兜底 = 单一最强簇（其他皮肤缺口缘占比更高时）。
    ``exclude_until`` 之前（初始拼图块区）与最左 4px（截图边框伪影）排除。
    """
    if w < 40 or h < 40:
        return None, 0.0
    gray = _to_gray(rows, w, h)
    col_edge = [0] * w
    for x in range(1, w):
        cnt = 0
        for y in range(h):
            d = gray[y][x] - gray[y][x - 1]
            if d < 0:
                d = -d
            if d > 26:
                cnt += 1
        col_edge[x] = cnt

    lo = max(exclude_until + 2, 4, int(w * 0.10))
    hi = int(w * 0.96)
    strong = max(12, int(h * 0.20))

    clusters = []
    start = last = None
    for x in range(lo, hi):
        if col_edge[x] >= strong:
            if start is None:
                start = last = x
            elif x - last <= 3:
                last = x
            else:
                clusters.append((start, last))
                start = last = x
    if start is not None:
        clusters.append((start, last))
    if not clusters:
        return None, 0.0

    def _peak(c):
        return max(col_edge[c[0]:c[1] + 1])

    px_per_css = max(dpr, 0.1)
    best = None  # (score, left_x)
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            dist_css = (clusters[j][0] - clusters[i][0]) / px_per_css
            if 35.0 <= dist_css <= 95.0:
                score = _peak(clusters[i]) + _peak(clusters[j])
                if best is None or score > best[0]:
                    best = (score, clusters[i][0])
    if best:
        return best[1], min(1.0, best[0] / (1.6 * h))

    strong_c = max(clusters, key=_peak)
    if _peak(strong_c) >= max(15, int(h * 0.3)):
        return strong_c[0], min(1.0, _peak(strong_c) / h)
    return None, 0.0


def _alpha_bbox(rows, w: int, h: int):
    """拼图 PNG 可见内容的 (x0, x1, y0, y1) 自然像素边界；全透明返回 None。"""
    xs = [x for x in range(w)
          if any(rows[y][x * 4 + 3] > 24 for y in range(h))]
    if not xs:
        return None
    ys = [y for y in range(h)
          if any(rows[y][x * 4 + 3] > 24 for x in range(w))]
    return xs[0], xs[-1], ys[0], ys[-1]


def locate_gap_by_template(bg_rows, bg_w: int, bg_h: int,
                           piece_rows, piece_pw: int, piece_ph: int,
                           piece_box: dict, bg_box: dict, dpr: float,
                           exclude_until: int = 0):
    """模板匹配定位缺口 → (gap_left_img_px | None, confidence)。

    原理（实测校准 2026-10-04：边缘簇法在真实图上置信度仅 ~0.3，易配到
    内容纹理）：拼图只水平滑动，缺口与拼图同一竖直带；取拼图 **alpha 轮廓
    环**样本点，在背景二值边缘图（|∇|>40，±1px 容差）上沿 x 扫**命中率**
    ——正确位置整圈轮廓与缺口轮廓重合（实测 0.81，远处次高 0.60）。
    幅度无关，对亮度/纹理不敏感；样本数百级 + 单行扫描，纯 Python 亚秒。
    """
    bbox = _alpha_bbox(piece_rows, piece_pw, piece_ph)
    if not bbox:
        return None, 0.0
    x0, x1, y0, y1 = bbox
    scale_css = piece_box["width"] / max(piece_pw, 1)   # 自然 → CSS
    s = scale_css * max(dpr, 0.1)                        # 自然 → 背景截图像素

    bg_gray = _to_gray(bg_rows, bg_w, bg_h)
    pc_gray = _to_gray(piece_rows, piece_pw, piece_ph)
    pc_alpha = [[piece_rows[y][x * 4 + 3] for x in range(piece_pw)]
                for y in range(piece_ph)]

    # 背景二值边缘图（阈值 40 ≈ 实测 p95；十字 1px 容差查表）
    edge = [bytearray(bg_w) for _ in range(bg_h)]
    for y in range(1, bg_h):
        grow, prow = bg_gray[y], bg_gray[y - 1]
        erow = edge[y]
        for x in range(1, bg_w):
            gx = grow[x] - grow[x - 1]
            if gx < 0:
                gx = -gx
            gy = prow[x] - grow[x]
            if gy < 0:
                gy = -gy
            if gx + gy > 40:
                erow[x] = 1

    def _hit(x: int, y: int) -> int:
        if x < 1 or y < 1 or x >= bg_w - 1 or y >= bg_h - 1:
            return 0
        return 1 if (edge[y][x] or edge[y][x - 1] or edge[y][x + 1]
                     or edge[y - 1][x] or edge[y + 1][x]) else 0

    # 轮廓样本：可见像素且 4 邻域含透明（形状信息在轮廓上，内部纹理与
    # 暗化缺口不匹配，只采样轮廓）
    def interior(nx: int, ny: int) -> bool:
        if nx <= 0 or ny <= 0 or nx >= piece_pw - 1 or ny >= piece_ph - 1:
            return False
        return (pc_alpha[ny - 1][nx] > 24 and pc_alpha[ny + 1][nx] > 24
                and pc_alpha[ny][nx - 1] > 24 and pc_alpha[ny][nx + 1] > 24)

    outline = []
    step = max(1, (x1 - x0) // 40)
    for ny in range(y0, y1 + 1, step):
        for nx in range(x0, x1 + 1, step):
            if pc_alpha[ny][nx] <= 24 or interior(nx, ny):
                continue
            outline.append((nx, ny))
    if len(outline) < 24:
        return None, 0.0

    tw_img = int((x1 - x0) * s)
    top_img = int((piece_box["y"] + y0 * scale_css - bg_box["y"]) * dpr)
    top_img = max(0, min(top_img, bg_h - 3))
    lo = max(exclude_until + 2, 4)
    hi = max(lo + 1, bg_w - tw_img - 2)

    rates = []
    for xc in range(lo, hi):
        hits = 0
        for nx, ny in outline:
            hits += _hit(int(xc + (nx - x0) * s),
                         int(top_img + (ny - y0) * s))
        rates.append((hits / len(outline), xc))
    if not rates:
        return None, 0.0
    best = max(rates, key=lambda t: t[0])
    if best[0] < 0.45:
        return None, best[0]
    # 区分度：±4px 邻峰是同一位置的抖动，不算竞争峰；真机实测
    # 真缺口 0.81 vs 远处次高 0.60
    far = [r for r in rates if abs(r[1] - best[1]) > 4]
    second = max(far, key=lambda t: t[0]) if far else (0.0, -1)
    if second[0] > best[0] * 0.8:
        return None, best[0]
    return best[1], best[0]



# ── 拟人轨迹（纯函数，单测覆盖）────────────────────────────────────

def build_drag_steps(distance: float, rng: random.Random):
    """生成拖拽轨迹：[(x_off, y_off, wait_ms)]，终点精确落在 distance。

    分段随机步长 + 中途迟疑 + 过冲回正（M0 复核过的人类特征；M0 结论
    表明指纹才是被拒主因，轨迹只需"不像机器"即可）。
    """
    distance = round(float(distance), 1)
    if distance <= 0:
        return []
    overshoot = rng.uniform(5, 14) if distance > 40 else 0.0
    phase1 = distance + overshoot
    steps = []
    x = y = 0.0
    while x < phase1 - 0.5:
        seg = min(phase1 - x, rng.uniform(9, 26))
        x += seg
        y = max(-3.0, min(3.0, y + rng.uniform(-1.6, 1.6)))
        steps.append((round(x, 1), round(y, 1), int(rng.uniform(12, 38))))
    # 中途迟疑（30%~70% 处某步加停顿）
    if len(steps) >= 8:
        idx = rng.randrange(len(steps) // 3, max(2 * len(steps) // 3, 1))
        dx_, dy_, dt_ = steps[idx]
        steps[idx] = (dx_, dy_, dt_ + int(rng.uniform(60, 220)))
    # 过冲后回拉
    while x > distance + 0.4:
        back = min(x - distance, rng.uniform(2.0, 6.0))
        x -= back
        y = max(-3.0, min(3.0, y + rng.uniform(-1.0, 1.0)))
        steps.append((round(x, 1), round(y, 1), int(rng.uniform(30, 90))))
    steps.append((distance, round(y, 1), int(rng.uniform(60, 150))))
    # 总时长约束 0.4s–1.6s：越界则整体缩放步间等待
    total = sum(s[2] for s in steps)
    if total < 400:
        factor = 400.0 / total
        steps = [(a, b, int(c * factor)) for a, b, c in steps]
    elif total > 1600:
        factor = 1600.0 / total
        steps = [(a, b, max(8, int(c * factor))) for a, b, c in steps]
    return steps


# ── stealth 指纹补丁 ──────────────────────────────────────────────

STEALTH_JS = r"""(() => {
  if (window.__zhsStealthApplied) return 'already';
  try { window.__zhsStealthApplied = true; } catch (e) {}
  // navigator.webdriver → false（真实 Chrome 非自动化下的取值）。
  // 原型级定义，frame 各 realm 由 addInitScript 自行覆盖。
  try {
    const proto = Object.getPrototypeOf(navigator);
    Object.defineProperty(proto, 'webdriver', {
      get: () => false, configurable: true, enumerable: true,
    });
    if (navigator.webdriver !== false) {
      Object.defineProperty(navigator, 'webdriver', {
        get: () => false, configurable: true,
      });
    }
  } catch (e) {}
  // window.chrome 完整性（真实 Chrome 存在；仅缺失时补桩）
  try {
    if (!window.chrome) window.chrome = {};
    if (!window.chrome.app) window.chrome.app = {
      isInstalled: false,
      InstallState: { DISABLED: 'disabled', INSTALLED: 'installed',
                      NOT_INSTALLED: 'not_installed' },
      RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run',
                      RUNNING: 'running' },
    };
    if (!window.chrome.runtime) window.chrome.runtime = {
      OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install',
                           OTHER: 'other' },
      PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux',
                    MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
      connect: function () {}, sendMessage: function () {},
    };
  } catch (e) {}
  // permissions.query 与 Notification.permission 一致性（无头特征项）
  try {
    const perm = window.navigator.permissions;
    const orig = perm.query.bind(perm);
    perm.query = (desc) => (desc && desc.name === 'notifications'
      ? Promise.resolve({
          state: (typeof Notification !== 'undefined'
                  && Notification.permission) || 'prompt',
          onchange: null,
        })
      : orig(desc));
  } catch (e) {}
  return 'ok';
})()"""


def _load_stealth_source() -> tuple[str, str]:
    """返回 (source, kind)：scripts/stealth.min.js 优先，内置 mini 版兜底。

    stealth.min.js 来源 berstend/puppeteer-extra（MIT，extract-stealth-evasions
    构建产物，经 CXRunfree/Autovisor 仓库分发）——2026-10-04 实测：mini 版
    补丁（webdriver/chrome/permissions）定位已准至 ±1px 仍被易盾拒绝，
    需完整版指纹修正（navigator/webgl/chrome/iframe 等十余模块）。
    """
    path = WORKSPACE / "scripts" / "stealth.min.js"
    try:
        src = path.read_text(encoding="utf-8")
        if len(src) > 10000:
            return src, "stealth.min.js"
        log(f"[slider] {path.name} 内容异常（{len(src)}B），用内置 mini 补丁", "WARN")
    except OSError:
        log("[slider] 未找到 scripts/stealth.min.js，用内置 mini 补丁", "WARN")
    return STEALTH_JS, "builtin-mini"


def inject_stealth() -> bool:
    """注入指纹补丁：当前页 addScriptTag + 后续导航 addInitScript。幂等。

    必须在易盾初始化**之前**完成（本仓库调用点：zhihuishu_login 开头，
    早于登录提交点击 → 早于验证码渲染）。完整版 stealth 为语句序列，
    不能走 evaluate（表达式语义）——当前页用 addScriptTag 以程序执行。
    """
    source, kind = _load_stealth_source()
    payload = json.dumps(source)
    js = ("async (page) => {"
          f"  await page.addInitScript({payload});"
          f"  await page.addScriptTag({{ content: {payload} }});"
          "  return 'stealth:' + " + json.dumps(kind) + "; }")
    try:
        raw = _run_js_file(js, timeout=25)
        log(f"[slider] stealth 指纹补丁已注入（{raw or kind}）")
        return True
    except Exception as e:
        log(f"[slider] stealth 注入失败（滑块通过率可能下降）：{e}", "WARN")
        return False


# ── 浏览器侧：探测 / 截图 / 拖拽 / 校验 ─────────────────────────────

_PROBE_JS = """
async (page) => {
  const r = await page.evaluate(() => {
    const mark = (el, name) => {
      if (el) { try { el.setAttribute('data-zhs-' + name, '1'); } catch (e) {} }
      return el;
    };
    const q = (s) => document.querySelector(s);
    const modal = q('.yidun_modal') || q('.yidun');
    const jigsaw = mark(q('img.yidun_jigsaw') || q('img[class*="jigsaw"]'),
                        'jigsaw');
    const bg = mark(q('img.yidun_bg-img') || q('.yidun_bg-img img')
                    || q('.yidun_bgimg img') || q('img[class*="yidun_bg"]')
                    || [...document.querySelectorAll('[class*="yidun"]')]
                        .find(el => {
                          const s = getComputedStyle(el).backgroundImage;
                          return s && s.includes('url');
                        }) || null, 'bg');
    const handler = mark(q('.yidun_handler')
                         || q('[class*="yidun_handler"]')
                         // 2.28.x：拖钮即 .yidun_slider（40×38），无 handler 类
                         || q('.yidun_slider'), 'handler');
    const track = mark(q('.yidun_control')
                       || q('[class*="yidun_control"]')
                       || q('.yidun_slider'), 'track');
    const box = (el) => el ? (() => {
      const b = el.getBoundingClientRect();
      return { x: +b.x.toFixed(1), y: +b.y.toFixed(1),
               width: +b.width.toFixed(1), height: +b.height.toFixed(1) };
    })() : null;
    const validate = q('input[name=NECaptchaValidate]')
                     || q('input[id*=NECaptcha i]');
    const shown = !!modal && modal.getClientRects().length > 0;
    return JSON.stringify({
      shown,
      dpr: window.devicePixelRatio || 1,
      jigsaw: jigsaw ? {
        box: box(jigsaw), src: (jigsaw.src || '').slice(0, 24),
        natural: { w: jigsaw.naturalWidth, h: jigsaw.naturalHeight },
      } : null,
      bg: bg ? { box: box(bg), tag: bg.tagName,
                 cls: String(bg.className).slice(0, 60) } : null,
      handler: handler ? { box: box(handler) } : null,
      track: track ? { box: box(track) } : null,
      validate: !!(validate && validate.value),
      tip: ((q('.yidun_tip') || q('[class*="yidun_tip"]') || {}).innerText
            || '').trim().slice(0, 24),
      url: location.href,
    });
  });
  return r;
}
"""


def _probe_captcha() -> dict | None:
    """探测易盾 DOM（并给关键元素打 data-zhs-* 标记）。"""
    try:
        raw = _run_js_file(_PROBE_JS, timeout=15)
        data = json.loads(raw or "{}")
        if isinstance(data, str):
            data = json.loads(data)
        return data
    except Exception as e:
        log(f"[slider] 探测失败：{e}", "WARN")
        return None


def _shoot_bg_element() -> tuple[str, dict] | None:
    """按标记截背景图 element 截图 → (png_path, probe_bg_info)。"""
    shot_path = (TMP_DIR / f"zhihuishu-slider-bg-{int(time.time() * 1000)}.png")
    shot_path.parent.mkdir(parents=True, exist_ok=True)
    js = ("async (page) => {"
          "  const el = await page.$('[data-zhs-bg]');"
          "  if (!el) return 'NOT_FOUND';"
          f"  await el.screenshot({{ path: {_js_str(shot_path.as_posix())} }});"
          "  return 'SHOT_OK'; }")
    try:
        raw = _run_js_file(js, timeout=30)
        if "SHOT_OK" not in (raw or ""):
            log(f"[slider] 背景截图未完成：{raw or '无输出'}", "WARN")
            return None
        return str(shot_path), {}
    except Exception as e:
        log(f"[slider] 背景截图失败：{e}", "WARN")
        return None


def _fetch_piece_png_b64() -> str | None:
    """取拼图 PNG（data URL 直取；http 走页内 fetch，失败返回 None）。"""
    js = """
async (page) => {
  const r = await page.evaluate(async () => {
    const img = document.querySelector('[data-zhs-jigsaw]');
    if (!img) return '';
    const src = img.currentSrc || img.src || '';
    if (!src) return '';
    if (src.startsWith('data:')) return src;
    try {
      const resp = await fetch(src);
      const u8 = new Uint8Array(await resp.arrayBuffer());
      let bin = '';
      for (let i = 0; i < u8.length; i++) bin += String.fromCharCode(u8[i]);
      return 'data:image/png;base64,' + btoa(bin);
    } catch (e) { return ''; }
  });
  return r;
}
"""
    try:
        raw = _run_js_file(js, timeout=20)
        val = (raw or "").strip()
        if val.startswith("data:"):
            return val.split(",", 1)[1]
        return None
    except Exception as e:
        log(f"[slider] 拼图获取失败：{e}", "WARN")
        return None


def _perform_drag(steps, pre_ms: int, post_ms: int,
                  target_piece_left: float | None = None,
                  piece_left_css_off: float = 0.0,
                  k_estimate: float = 0.9) -> bool:
    """CDP 真实鼠标事件回放轨迹；给 ``target_piece_left`` 时闭环校正。

    实测标定（2026-10-04 真机）：易盾**滑钮位移≠拼图位移**（k≈0.88），
    1:1 拖拽会系统性欠冲 ~12% 而必被拒。主轨迹按 1/k 估计行程，按住不
    放读拼图实际左缘（boundingBox），每轮 err/k 校正，|err|≤1.2px 收敛
    后释放——对 k 的站点/窗口差异自适应，中途停顿本身也是人类特征。
    """
    js = ("async (page) => {"
          "  const h = await page.$('[data-zhs-handler]');"
          "  if (!h) return 'NO_HANDLER';"
          "  const j = await page.$('img.yidun_jigsaw')"
          "    || await page.$('[data-zhs-jigsaw]');"
          "  const hb = await h.boundingBox();"
          "  if (!hb) return 'NO_BOX';"
          f"  const target = {json.dumps(target_piece_left)};"
          f"  const pOff = {float(piece_left_css_off):.2f};"
          f"  const k = {float(k_estimate):.3f};"
          "  const sx = hb.x + hb.width / 2, sy = hb.y + hb.height / 2;"
          f"  const steps = {json.dumps(steps)};"
          "  await page.mouse.move(sx, sy);"
          f"  await page.waitForTimeout({int(pre_ms)});"
          "  await page.mouse.down();"
          "  let mx = sx;"
          "  for (const [dx, dy, dt] of steps) {"
          "    mx = sx + dx;"
          "    await page.mouse.move(mx, sy + dy);"
          "    if (dt > 0) await page.waitForTimeout(dt);"
          "  }"
          "  let note = 'open';"
          "  if (target !== null && j) {"
          "    note = '';"
          "    for (let i = 0; i < 3; i++) {"
          "      await page.waitForTimeout(140);"
          "      const jb = await j.boundingBox();"
          "      if (!jb) { note += 'noJb;'; break; }"
          "      const err = target - (jb.x + pOff);"
          "      note += 'err' + i + '=' + err.toFixed(1) + ';';"
          "      if (Math.abs(err) <= 1.2) break;"
          "      const dc = err / k;"
          "      const n = Math.max(2, Math.min(6, Math.ceil(Math.abs(dc) / 6)));"
          "      for (let s = 1; s <= n; s++) {"
          "        mx += dc / n;"
          "        await page.mouse.move(mx, sy + (Math.random() * 2 - 1));"
          "        await page.waitForTimeout(25 + Math.random() * 45);"
          "      }"
          "    }"
          "  }"
          "  /* 释放前手部微颤：无移动停顿是机器特征 */"
          "  for (let w = 0; w < 2; w++) {"
          "    await page.mouse.move(mx + (Math.random() * 1.2 - 0.6),"
          "        sy + (Math.random() * 1.6 - 0.8));"
          "    await page.waitForTimeout(40 + Math.random() * 70);"
          "  }"
          f"  await page.waitForTimeout({int(post_ms)});"
          "  await page.mouse.up();"
          "  return 'dragged:' + steps.length + '|' + note; }")
    try:
        raw = _run_js_file(js, timeout=40)
        ok = "dragged:" in (raw or "")
        if not ok:
            log(f"[slider] 拖拽未执行：{raw or '无输出'}", "WARN")
        elif "err" in (raw or ""):
            log(f"[slider] 闭环校正：{(raw or '').split('|', 1)[-1]}")
        return ok
    except Exception as e:
        log(f"[slider] 拖拽异常：{e}", "WARN")
        return False


_CHECK_JS = """
async (page) => {
  const r = await page.evaluate(() => {
    const q = (s) => document.querySelector(s);
    const modal = q('.yidun_modal') || q('.yidun');
    const validate = q('input[name=NECaptchaValidate]')
                     || q('input[id*=NECaptcha i]');
    const tip = q('.yidun_tip') || q('[class*="yidun_tip"]');
    return JSON.stringify({
      shown: !!modal && modal.getClientRects().length > 0,
      validate: !!(validate && validate.value),
      tip: ((tip || {}).innerText || '').trim().slice(0, 24),
      url: location.href,
    });
  });
  return r;
}
"""


def _check_result() -> dict:
    try:
        raw = _run_js_file(_CHECK_JS, timeout=15)
        data = json.loads(raw or "{}")
        if isinstance(data, str):
            data = json.loads(data)
        return data
    except Exception as e:
        log(f"[slider] 结果校验失败：{e}", "WARN")
        return {"shown": True, "validate": False, "tip": "", "url": "", "err": str(e)}


def _js_str(s: str) -> str:
    return json.dumps(s)


# ── 编排 ──────────────────────────────────────────────────────────

def _auto_enabled() -> bool:
    flag = os.environ.get("ZHIHUISHU_SLIDER_AUTO", "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return bool(cfg("zhihuishu_slider.auto_solve", True))


def _max_attempts() -> int:
    env = os.environ.get("ZHIHUISHU_SLIDER_ATTEMPTS", "").strip()
    if env.isdigit():
        return max(1, int(env))
    return max(1, int(cfg("zhihuishu_slider.max_attempts", 3)))


def wait_slider_modal(timeout_s: float = 8.0) -> dict | None:
    """轮询等待易盾弹窗出现（提交登录后到弹窗有网络延迟）。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        probe = _probe_captcha()
        if probe and probe.get("shown"):
            return probe
        time.sleep(0.8)
    return None


def _retrigger_captcha() -> bool:
    """连续失败后易盾可能直接收起弹窗：再点一次登录按钮重新触发。"""
    from core.browser.engine import pw
    try:
        pw("click", "div.btn-block__grandient_login",
           timeout=cfg("timeouts.click_action", 10))
        log("[slider] 已重新点击登录按钮触发验证码")
        return True
    except Exception as e:
        log(f"[slider] 重新触发验证码失败：{e}", "WARN")
        return False


def _solve_once() -> bool:
    """单次求解：探测 → 截图定位 → 计算位移 → 拖拽 → 校验。"""
    probe = _probe_captcha()
    if not probe or not probe.get("shown"):
        st = _check_result()
        url = st.get("url") or ""
        if (st.get("validate") or "成功" in (st.get("tip") or "")
                or (url and "login.zhihuishu.com" not in url)):
            log(f"[slider] 验证已通过（弹窗收起，url={url[:50]}）")
            return True
        # 弹窗被易盾收起 → 重新触发再战
        if _retrigger_captcha():
            time.sleep(1.5)
            probe = wait_slider_modal(8.0)
        if not probe or not probe.get("shown"):
            log("[slider] 弹窗未能重新触发", "WARN")
            return False
    bg = probe.get("bg") or {}
    jigsaw = probe.get("jigsaw") or {}
    handler = probe.get("handler") or {}
    if not bg.get("box") or not handler.get("box"):
        log("[slider] 背景或滑钮几何缺失，跳过本轮", "WARN")
        return False
    dpr = float(probe.get("dpr") or 1)

    # 拼图 PNG：alpha 可见边界（左缘=位移基准，右缘=排除区右界）+ 模板数据
    alpha_left = alpha_right = None
    piece_pixels = None   # (rows, w, h)
    natural_w = (jigsaw.get("natural") or {}).get("w") or 0
    piece_b64 = _fetch_piece_png_b64()
    if piece_b64:
        try:
            pw_, ph_, prows = decode_png(base64.b64decode(piece_b64))
            bbox = _alpha_bbox(prows, pw_, ph_)
            if bbox:
                alpha_left, alpha_right = bbox[0], bbox[1]
            piece_pixels = (prows, pw_, ph_)
            natural_w = natural_w or pw_
            if os.environ.get("ZHIHUISHU_SLIDER_DEBUG", "0") == "1":
                keep_p = TMP_DIR / f"slider-piece-{int(time.time() * 1000)}.png"
                try:
                    keep_p.write_bytes(base64.b64decode(piece_b64))
                except OSError:
                    pass
        except (PngError, struct.error, zlib.error, ValueError) as e:
            log(f"[slider] 拼图解码失败（按元素边界近似）：{e}", "WARN")

    shot = _shoot_bg_element()
    if not shot:
        return False
    path, _ = shot
    try:
        with open(path, "rb") as f:
            data = f.read()
        w, h, rows = decode_png(data)
    except (OSError, PngError, struct.error, zlib.error) as e:
        log(f"[slider] 背景图解码失败：{e}", "WARN")
        return False
    finally:
        # 排障模式保留截图（ZHIHUISHU_SLIDER_DEBUG=1，入 data/temp）
        if os.environ.get("ZHIHUISHU_SLIDER_DEBUG", "0") == "1":
            keep = TMP_DIR / f"slider-bg-fail-{int(time.time() * 1000)}.png"
            try:
                os.replace(path, keep)
                log(f"[slider] 排障：背景图留存 {keep.name}")
            except OSError:
                pass
        else:
            try:
                os.unlink(path)
            except OSError:
                pass

    # 排除区：初始拼图块可见右缘（拼图自身有强边缘，不排除会误检）
    scale = jigsaw["box"]["width"] / max(natural_w, 1)
    if alpha_right is not None:
        piece_right_css = jigsaw["box"]["x"] + alpha_right * scale
        exclude = int((piece_right_css - bg["box"]["x"]) * dpr) + 6
    elif jigsaw.get("box"):
        exclude = int((jigsaw["box"]["x"] + jigsaw["box"]["width"]
                       - bg["box"]["x"]) * dpr) + 6
    else:
        exclude = int(w * 0.25)

    # 主通道：拼图轮廓模板匹配；兜底：边缘簇配对
    gap_x = conf = None
    how = ""
    if piece_pixels and jigsaw.get("box"):
        prows_, ppw_, pph_ = piece_pixels
        gap_x, conf = locate_gap_by_template(
            rows, w, h, prows_, ppw_, pph_,
            jigsaw["box"], bg["box"], dpr, exclude_until=exclude)
        how = "模板匹配"
    if gap_x is None:
        gap_x, conf = locate_gap_x(rows, w, h, exclude_until=exclude, dpr=dpr)
        how = "边缘簇"
    if gap_x is None:
        log(f"[slider] 缺口定位失败（排除区 {exclude}px）", "WARN")
        return False
    log(f"[slider] 缺口定位[{how}] x={gap_x}px（宽 {w}×{h}，置信度 {conf:.2f}）")

    if not natural_w:
        natural_w = jigsaw["box"]["width"] if jigsaw.get("box") else 1
    target_left_css = bg["box"]["x"] + gap_x / max(dpr, 0.1)
    piece_off_css = (alpha_left or 0) * scale
    piece_cur_left = jigsaw["box"]["x"] + piece_off_css
    need = target_left_css - piece_cur_left
    # k（滑钮→拼图位移比）实测 ≈0.88：主轨迹按 1/0.9 估行程，闭环校正兜底
    dx_est = need / 0.9
    track = (probe.get("track") or {}).get("box")
    if track:
        dx_est = min(dx_est, track["width"] - handler["box"]["width"] - 4)
    dx_est = round(dx_est, 1)
    if not (8 <= dx_est <= 340):
        log(f"[slider] 位移异常 need={need:.1f}px（估计行程 {dx_est}px），放弃本轮",
            "WARN")
        return False
    log(f"[slider] 目标拼图左缘 {target_left_css:.1f}px（当前 {piece_cur_left:.1f}，"
        f"需移 {need:.1f}px，估计滑钮行程 {dx_est}px）")

    # 拖拽前背景 src 指纹：失败后 src 变化 = 易盾真实判定过一次落点
    src_before = _bg_src_fingerprint()
    rng = random.Random()
    steps = build_drag_steps(dx_est, rng)
    if not _perform_drag(steps, pre_ms=int(rng.uniform(120, 320)),
                         post_ms=int(rng.uniform(90, 240)),
                         target_piece_left=round(target_left_css, 1),
                         piece_left_css_off=piece_off_css,
                         k_estimate=0.9):
        return False
    # 结果判定要轮询：validate 填充/页面跳转可能晚于落点 2-5s
    # （2026-10-04 真机：err1=1.1px 落点已过，一次性检查误判失败）
    deadline = time.time() + 8.0
    last_tip = ""
    while time.time() < deadline:
        st = _check_result()
        tip = st.get("tip") or ""
        last_tip = tip
        url = st.get("url") or ""
        if st.get("validate") or "成功" in tip:
            log("[slider] ✔ 易盾验证通过")
            return True
        if not st.get("shown") and url and "login.zhihuishu.com" not in url:
            log(f"[slider] ✔ 验证通过（页面已跳转 {url[:60]}）")
            return True
        if st.get("shown") and _bg_src_fingerprint() != src_before:
            log("[slider] 图已刷新 = 落点被拒，提前进入重试", "WARN")
            return False
        time.sleep(0.8)
    log(f"[slider] 本轮未通过（tip={last_tip!r}），等待重试", "WARN")
    return False


def _bg_src_fingerprint() -> str:
    """背景图当前 src（失败刷新会换 URL，用作「判定已发生」的证据）。"""
    js = ("async (page) => { const r = await page.evaluate(() => {"
          " const el = document.querySelector('img.yidun_bg-img')"
          "   || document.querySelector('[class*=\"yidun_bg\"] img')"
          "   || document.querySelector('img[class*=\"yidun_bg\"]');"
          " return el ? (el.src || '') : ''; }); return r; }")
    try:
        return (_run_js_file(js, timeout=10) or "").strip()[-48:]
    except Exception:
        return ""


def auto_solve_slider(account_index: int = 0, max_attempts: int | None = None) -> bool:
    """易盾滑块自动求解入口。True = 验证通过（或无需验证）。

    失败/禁用时返回 False，调用方回退人工工单（auth.py 兜底链不变）。
    """
    if not _auto_enabled():
        log("[slider] 自动求解已禁用（ZHIHUISHU_SLIDER_AUTO / 配置）")
        return False
    attempts = max_attempts or _max_attempts()
    log(f"[slider] 易盾自动求解启用（账号 {account_index}，最多 {attempts} 次）")

    if not wait_slider_modal(8.0):
        st = _check_result()
        if st.get("validate") or "成功" in (st.get("tip") or ""):
            log("[slider] 滑块已处于通过状态")
            return True
        log("[slider] 未检测到易盾弹窗", "WARN")
        return False

    for i in range(1, attempts + 1):
        log(f"[slider] 第 {i}/{attempts} 次尝试...")
        try:
            if _solve_once():
                return True
        except Exception as e:
            log(f"[slider] 尝试异常：{e}", "WARN")
        # 失败后易盾会刷新背景图，等稳定再探测
        time.sleep(1.4 + random.uniform(0.4, 1.2))
    log(f"[slider] {attempts} 次尝试未通过，回退人工", "WARN")
    return False
