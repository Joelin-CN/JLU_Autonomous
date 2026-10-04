"""易盾滑块自动求解单元测试：PNG 解码 / 缺口定位 / 轨迹生成 / 位移计算。"""

import random
import struct
import zlib

import pytest

from platforms.zhihuishu.slider import (
    PngError, STEALTH_JS, _alpha_bbox, build_drag_steps,
    decode_png, locate_gap_by_template, locate_gap_x,
)


# ── PNG 编码助手（测试侧构造合成图）─────────────────────────────────

def _png_chunk(ctype: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + ctype + payload
            + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF))


def _encode_png(w: int, h: int, rows_rgba, filter_type: int = 0) -> bytes:
    """rows_rgba: [(r,g,b,a)×w]×h → PNG（位深 8 / RGBA / 单一过滤器）。"""
    raw = bytearray()
    prev = bytes(w * 4)
    for row in rows_rgba:
        line = bytearray()
        for px in row:
            line += bytes(px)
        out = bytearray(line)
        if filter_type == 1:  # Sub（按 4 字节色通道差分）
            for i in range(len(line) - 1, 3, -1):
                out[i] = (line[i] - line[i - 4]) & 0xFF
        elif filter_type == 2:  # Up
            for i in range(len(line)):
                out[i] = (line[i] - prev[i]) & 0xFF
        raw.append(filter_type)
        raw += out
        prev = bytes(line)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", zlib.compress(bytes(raw)))
            + _png_chunk(b"IEND", b""))


class TestPngDecode:
    def test_roundtrip_filter_none(self):
        w, h = 5, 3
        rows = [[(x * 10 % 256, y * 40 % 256, (x + y) % 256, 255)
                 for x in range(w)] for y in range(h)]
        data = _encode_png(w, h, rows)
        dw, dh, drows = decode_png(data)
        assert (dw, dh) == (w, h)
        for y in range(h):
            for x in range(w):
                assert tuple(drows[y][x * 4:x * 4 + 4]) == rows[y][x]

    def test_roundtrip_filter_up(self):
        w, h = 8, 4
        rows = [[(x * 31 % 256, y * 57 % 256, (x * y) % 256, 255)
                 for x in range(w)] for y in range(h)]
        data = _encode_png(w, h, rows, filter_type=2)
        dw, dh, drows = decode_png(data)
        assert (dw, dh) == (w, h)
        for y in range(h):
            for x in range(w):
                assert tuple(drows[y][x * 4:x * 4 + 4]) == rows[y][x]

    def test_alpha_preserved(self):
        rows = [[(10, 20, 30, 0), (40, 50, 60, 200)]]
        _w, _h, drows = decode_png(_encode_png(2, 1, rows))
        assert drows[0][3] == 0 and drows[0][7] == 200

    def test_rejects_non_png(self):
        with pytest.raises(PngError):
            decode_png(b"not a png at all")

    def test_rejects_interlaced(self):
        ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 1)
        data = (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr)
                + _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
                + _png_chunk(b"IEND", b""))
        with pytest.raises(PngError):
            decode_png(data)


# ── 缺口定位 ─────────────────────────────────────────────────────

def _synthetic_bg(w=320, h=160, gap_left=210, gap_w=58, piece_right=64):
    """纹理背景 + 暗色缺口 + 左侧初始拼图块（半透明覆盖）。"""
    rows = []
    for y in range(h):
        row = bytearray(w * 4)
        for x in range(w):
            v = 120 + (x * 7 + y * 3) % 40  # 有梯度的伪照片
            if gap_left <= x < gap_left + gap_w and 30 <= y < 30 + 66:
                v = 56  # 缺口内部显著偏暗
            if x < piece_right and 28 <= y < 28 + 70:
                v = (v + 170) // 2  # 拼图块覆盖（同样有强边缘）
            row[x * 4:x * 4 + 4] = bytes((v, v, v, 255))
        rows.append(bytes(row))
    return rows


class TestLocateGap:
    def test_finds_gap_left_edge(self):
        w, h = 320, 160
        rows = _synthetic_bg(w, h, gap_left=210)
        gap_x, conf = locate_gap_x(rows, w, h, exclude_until=68)
        assert gap_x is not None
        assert abs(gap_x - 210) <= 4
        assert conf > 0.3

    def test_exclusion_zone_blocks_piece_edge(self):
        """不排除初始拼图块时，块右缘会抢 argmax——接口必须可排除。"""
        w, h = 320, 160
        rows = _synthetic_bg(w, h, gap_left=210, piece_right=64)
        no_excl, _ = locate_gap_x(rows, w, h, exclude_until=0)
        # 无论是否误中块缘，带排除区的结果必须正确
        gap_x, _ = locate_gap_x(rows, w, h, exclude_until=70)
        assert abs(gap_x - 210) <= 4
        # 佐证：零排除时结果确实会被块缘带偏（或仍正确，但不能比排除版差）
        if no_excl is not None:
            assert abs(gap_x - 210) <= abs(no_excl - 210) + 1

    def test_gap_position_variants(self):
        w, h = 320, 160
        for gap_left in (150, 185, 240):
            rows = _synthetic_bg(w, h, gap_left=gap_left)
            gap_x, _ = locate_gap_x(rows, w, h, exclude_until=70)
            assert gap_x is not None
            assert abs(gap_x - gap_left) <= 4, f"gap_left={gap_left}, got {gap_x}"

    def test_no_gap_returns_none_or_low_conf(self):
        w, h = 160, 120
        rows = []
        for y in range(h):
            row = bytearray(w * 4)
            for x in range(w):
                v = 100 + (x * 3 + y * 5) % 30  # 平滑渐变，无暗带无强边
                row[x * 4:x * 4 + 4] = bytes((v, v, v, 255))
            rows.append(bytes(row))
        gap_x, conf = locate_gap_x(rows, w, h, exclude_until=20)
        assert gap_x is None or conf < 0.5


class TestTemplateMatch:
    @staticmethod
    def _synthetic_pair(gap_left=210, gap_w=58, gap_h=66):
        """背景（含暗缺口）+ 拼图 PNG（亮纹理，带透明边距）。"""
        bg_rows = []
        for y in range(160):
            row = bytearray(320 * 4)
            for x in range(320):
                v = 120 + (x * 7 + y * 3) % 40
                if gap_left <= x < gap_left + gap_w and 30 <= y < 30 + gap_h:
                    v = 56
                row[x * 4:x * 4 + 4] = bytes((v, v, v, 255))
            bg_rows.append(bytes(row))
        # 拼图自然 70x90，可见区 x 5..62 / y 12..77（与缺口同尺寸）
        pc_rows = []
        for y in range(90):
            row = bytearray(70 * 4)
            for x in range(70):
                if 5 <= x < 5 + gap_w and 12 <= y < 12 + gap_h:
                    v = 190 + (x + y) % 20
                    row[x * 4:x * 4 + 4] = bytes((v, v, v, 255))
                else:
                    row[x * 4:x * 4 + 4] = bytes((0, 0, 0, 0))
            pc_rows.append(bytes(row))
        # piece_box 令可见顶缘对齐缺口顶缘 y=30（scale_css=1）
        piece_box = {"x": 0.0, "y": 18.0, "width": 70.0, "height": 90.0}
        bg_box = {"x": 0.0, "y": 0.0, "width": 320.0, "height": 160.0}
        return bg_rows, pc_rows, piece_box, bg_box

    def test_finds_gap(self):
        bg, pc, pbox, bbox = self._synthetic_pair(gap_left=210)
        gap_x, conf = locate_gap_by_template(
            bg, 320, 160, pc, 70, 90, pbox, bbox, dpr=1.0, exclude_until=70)
        assert gap_x is not None
        assert abs(gap_x - 210) <= 4, f"got {gap_x}"
        assert conf > 0.1

    def test_gap_position_variants(self):
        for gap_left in (150, 185, 240):
            bg, pc, pbox, bbox = self._synthetic_pair(gap_left=gap_left)
            gap_x, _ = locate_gap_by_template(
                bg, 320, 160, pc, 70, 90, pbox, bbox, dpr=1.0, exclude_until=70)
            assert gap_x is not None
            assert abs(gap_x - gap_left) <= 4, f"want {gap_left}, got {gap_x}"

    def test_fully_transparent_piece_rejected(self):
        bg, _pc, pbox, bbox = self._synthetic_pair()
        empty = [bytes(70 * 4) for _ in range(90)]
        assert locate_gap_by_template(
            bg, 320, 160, empty, 70, 90, pbox, bbox, 1.0, 70) == (None, 0.0)


class TestAlphaBbox:
    def test_bbox(self):
        w, h = 90, 60
        rows = []
        for y in range(h):
            row = bytearray(w * 4)
            for x in range(w):
                if 4 <= x <= 87 and 2 <= y <= 50:
                    row[x * 4:x * 4 + 4] = bytes((9, 9, 9, 255))
            rows.append(bytes(row))
        assert _alpha_bbox(rows, w, h) == (4, 87, 2, 50)

    def test_transparent_none(self):
        rows = [bytes(20 * 4) for _ in range(10)]
        assert _alpha_bbox(rows, 20, 10) is None




# ── 拟人轨迹 ─────────────────────────────────────────────────────

class TestDragSteps:
    def test_ends_exactly_at_distance(self):
        for dist in (60, 120, 200):
            steps = build_drag_steps(dist, random.Random(7))
            assert steps[-1][0] == dist
            assert steps[-1][1] == steps[-1][1]  # y 携带

    def test_deterministic_with_seed(self):
        a = build_drag_steps(150, random.Random(42))
        b = build_drag_steps(150, random.Random(42))
        assert a == b

    def test_bounds_and_shape(self):
        steps = build_drag_steps(150, random.Random(1))
        assert len(steps) >= 12
        xs = [s[0] for s in steps]
        assert max(xs) <= 150 + 20          # 过冲上限
        assert min(xs) >= 0
        assert all(-4 <= s[1] <= 4 for s in steps)  # y 抖动窄幅
        total_ms = sum(s[2] for s in steps)
        assert 350 <= total_ms <= 1700      # 总时长人类区间（含缩放容差）

    def test_zero_distance_empty(self):
        assert build_drag_steps(0, random.Random(3)) == []

    def test_overshoot_then_pullback_exists_sometimes(self):
        # 多个种子下应至少出现过冲形态（不是每个种子必有，但常见）
        seen = any(
            max(s[0] for s in build_drag_steps(180, random.Random(s))) > 180
            for s in range(20)
        )
        assert seen


# ── stealth 脚本 ─────────────────────────────────────────────────

class TestStealthScript:
    def test_targets_webdriver(self):
        assert "'webdriver'" in STEALTH_JS or '"webdriver"' in STEALTH_JS
        assert "get: () => false" in STEALTH_JS

    def test_is_iife_and_idempotent(self):
        assert STEALTH_JS.startswith("(() => {")
        assert STEALTH_JS.rstrip().endswith("})()")
        assert "__zhsStealthApplied" in STEALTH_JS  # 幂等护栏

    def test_covers_chrome_and_permissions(self):
        assert "window.chrome" in STEALTH_JS
        assert "permissions" in STEALTH_JS

    def test_no_syntax_breaking_backticks(self):
        assert "`" not in STEALTH_JS  # PowerShell/cmd 转义雷区


class TestStealthAsset:
    def test_full_stealth_shipped(self):
        """完整版 stealth.min.js 必须随仓库/安装包（缺失会静默降级 mini 补丁，
        滑块通过率显著下降——2026-10-04 真机对照结论）。"""
        from core.constants import WORKSPACE
        p = WORKSPACE / "scripts" / "stealth.min.js"
        assert p.exists(), (
            "scripts/stealth.min.js 缺失——打包白名单/新克隆遗漏？")
        assert p.stat().st_size > 10000
