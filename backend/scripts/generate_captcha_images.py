#!/usr/bin/env python3
"""
Generate synthetic CAPTCHA test images for the OCR pipeline.

Creates diverse PNG images in tests/fixtures/captcha/ that simulate
real CAPTCHA challenges, plus an expected_answers.json metadata file.

Usage:
    python scripts/generate_captcha_images.py
"""

import json
import os
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps


# ── Configuration ──────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "tests" / "fixtures" / "captcha"

IMAGE_WIDTH = 200
IMAGE_HEIGHT = 80

# Available Windows fonts (first match wins)
FONT_CANDIDATES = [
    "arial.ttf",
    "times.ttf",
    "cour.ttf",
    "courbd.ttf",
    "arialbd.ttf",
]

# Try to find fonts; fall back to Pillow default
FONT_PATHS = []
_WIN_FONTS = Path("C:/Windows/Fonts")
for _name in FONT_CANDIDATES:
    _p = _WIN_FONTS / _name
    if _p.exists():
        FONT_PATHS.append(str(_p))

# ── Visual style presets ───────────────────────────────────────────────────

BACKGROUND_COLORS = {
    "white": (255, 255, 255),
    "light_gray": (230, 230, 230),
    "light_yellow": (255, 255, 220),
    "light_blue": (220, 235, 255),
}

TEXT_COLORS = {
    "black": (0, 0, 0),
    "dark_blue": (0, 0, 140),
    "dark_red": (180, 0, 0),
    "dark_green": (0, 100, 0),
    "dark_purple": (100, 0, 120),
    "dark_orange": (180, 80, 0),
}

# ── CAPTCHA definitions ────────────────────────────────────────────────────

# Each entry: (answer_text, font_size, bg_color_key, text_color_key,
#               add_noise, add_lines, rotation_degrees, apply_blur, x_offset)
CAPTCHA_DEFS = [
    # ── 4-char alphanumeric (most common) ──────────────────────────────
    ("A3x9", 36, "white", "black", True, True, 0, False, 0),
    ("X7k2", 40, "light_gray", "dark_blue", True, False, 0, False, 0),
    ("NSdn", 32, "light_yellow", "dark_red", False, True, 0, False, 0),
    ("ABc1", 44, "light_blue", "dark_green", True, True, 0, False, 0),
    ("Mn2P", 36, "white", "dark_purple", False, False, 0, True, 0),
    ("K9aR", 28, "light_gray", "black", True, False, 5, False, 0),
    ("zT5q", 38, "light_yellow", "dark_blue", True, True, -8, False, 5),
    ("H4mW", 42, "white", "dark_orange", False, True, 0, False, -5),
    ("r6Pj", 34, "light_blue", "dark_red", True, False, 10, True, 0),
    ("B8vL", 48, "light_gray", "black", False, False, 0, False, 0),

    # ── 5-char alphanumeric ────────────────────────────────────────────
    ("K9mP2", 32, "white", "black", True, True, 0, False, 0),
    ("R7xQ4", 30, "light_yellow", "dark_blue", True, False, -3, False, 0),

    # ── 6-char alphanumeric ────────────────────────────────────────────
    ("R7tY3w", 26, "light_gray", "dark_green", True, True, 0, False, 0),
    ("A2sD9f", 28, "light_blue", "dark_red", False, True, 0, False, 0),

    # ── 3-char alphanumeric ────────────────────────────────────────────
    ("x9Z", 48, "white", "dark_purple", True, False, 0, True, 0),
    ("K3b", 44, "light_yellow", "black", False, True, 0, False, 0),

    # ── Numbers only ───────────────────────────────────────────────────
    ("3847", 36, "white", "dark_red", True, True, 0, False, 0),
    ("5920", 40, "light_gray", "dark_blue", True, False, 5, False, 0),

    # ── Mixed case edge cases ──────────────────────────────────────────
    # Ambiguous chars (I/l/1, O/0, etc.)
    ("I1l0", 34, "white", "black", True, True, 0, False, 0),
    ("O0oQ", 36, "light_yellow", "dark_green", False, True, 0, False, 0),
    ("S5s8", 38, "light_blue", "dark_blue", True, False, 8, False, 0),
    ("Z2z7", 32, "light_gray", "dark_red", True, True, -5, True, 0),

    # ── Extra diverse styles ───────────────────────────────────────────
    ("qW4y", 40, "white", "black", True, False, 0, False, -8),
    ("Xp9M", 36, "light_blue", "dark_orange", False, True, 0, False, 0),
]


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return a PIL font at the requested size."""
    if FONT_PATHS:
        # Pick a random available font to add variety
        fp = random.choice(FONT_PATHS)
        return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def _add_noise_dots(draw: ImageDraw.ImageDraw, width: int, height: int, count: int = 80) -> None:
    """Draw random colored noise dots."""
    for _ in range(count):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        color = tuple(random.randint(0, 180) for _ in range(3))
        draw.point((x, y), fill=color)


def _add_lines(draw: ImageDraw.ImageDraw, width: int, height: int, count: int = 3) -> None:
    """Draw random lines across the image."""
    for _ in range(count):
        x1 = random.randint(0, width - 1)
        y1 = random.randint(0, height - 1)
        x2 = random.randint(0, width - 1)
        y2 = random.randint(0, height - 1)
        color = tuple(random.randint(50, 200) for _ in range(3))
        draw.line((x1, y1, x2, y2), fill=color, width=random.randint(1, 2))


def generate_one(answer: str,
                 font_size: int,
                 bg_color: tuple[int, int, int],
                 text_color: tuple[int, int, int],
                 add_noise: bool,
                 add_lines: bool,
                 rotation: float,
                 apply_blur: bool,
                 x_offset: int,
                 ) -> Image.Image:
    """Generate a single CAPTCHA image and return the PIL Image."""
    img = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), bg_color)
    draw = ImageDraw.Draw(img)
    font = _get_font(font_size)

    # Measure text to center it
    bbox = draw.textbbox((0, 0), answer, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (IMAGE_WIDTH - tw) // 2 + x_offset
    y = (IMAGE_HEIGHT - th) // 2 - bbox[1]  # bbox[1] is top offset

    # Draw each character individually with slight vertical jitter for realism
    char_x = x
    for ch in answer:
        ch_box = draw.textbbox((0, 0), ch, font=font)
        ch_w = ch_box[2] - ch_box[0]
        jitter_y = random.randint(-2, 2)
        draw.text((char_x, y + jitter_y), ch, fill=text_color, font=font)
        char_x += ch_w

    # Apply rotation if needed
    if rotation != 0:
        img = img.rotate(rotation, resample=Image.BICUBIC, expand=False,
                         fillcolor=bg_color)

    # Add noise and lines after rotation
    draw = ImageDraw.Draw(img)
    if add_noise:
        _add_noise_dots(draw, IMAGE_WIDTH, IMAGE_HEIGHT, count=random.randint(40, 100))
    if add_lines:
        _add_lines(draw, IMAGE_WIDTH, IMAGE_HEIGHT, count=random.randint(1, 4))

    # Apply blur
    if apply_blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.5, 1.2)))

    return img


def main() -> int:
    print(f"Output directory: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    answers: dict[str, str] = {}
    total_size = 0

    for i, (answer, font_size, bg_key, text_color_key,
            add_noise, add_lines, rotation, apply_blur, x_offset) in enumerate(CAPTCHA_DEFS):
        filename = f"captcha_{answer}.png"
        filepath = OUTPUT_DIR / filename

        bg_color = BACKGROUND_COLORS[bg_key]
        text_color = TEXT_COLORS[text_color_key]

        img = generate_one(answer, font_size, bg_color, text_color,
                           add_noise, add_lines, rotation, apply_blur, x_offset)

        # Handle potential filename collisions by appending a suffix
        if filepath.exists():
            base = f"captcha_{answer}"
            filepath = OUTPUT_DIR / f"{base}_{i}.png"
            filename = filepath.name

        img.save(filepath, "PNG")
        fsize = filepath.stat().st_size
        total_size += fsize
        answers[filename] = answer

        noise_str = "noise" if add_noise else "clean"
        line_str = "lines" if add_lines else "no-lines"
        blur_str = "blur" if apply_blur else "sharp"
        rot_str = f"rot{rotation}" if rotation else ""
        style_desc = " ".join(filter(None, [noise_str, line_str, blur_str, rot_str,
                                            f"{font_size}px", f"offset{x_offset}"]))
        print(f"  [{i+1:02d}] {filename:<22s} answer={answer:<8s} | {style_desc} | {fsize:>5d} bytes")

    # Write expected_answers.json
    answers_path = OUTPUT_DIR / "expected_answers.json"
    with open(answers_path, "w", encoding="utf-8") as f:
        json.dump(answers, f, indent=2, ensure_ascii=False)
    print(f"\nMetadata written to: {answers_path}")

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Images generated : {len(answers)}")
    print(f"  Total size       : {total_size:,} bytes ({total_size / 1024:.1f} KB)")
    print(f"  Output directory : {OUTPUT_DIR}")
    print(f"  Answers file     : {answers_path}")

    # Verify all images are valid PNGs >100 bytes
    print(f"\nVERIFICATION")
    failures = 0
    for filename in sorted(answers.keys()):
        fp = OUTPUT_DIR / filename
        if not fp.exists():
            print(f"  FAIL: {filename} — file does not exist")
            failures += 1
        elif fp.stat().st_size < 100:
            print(f"  FAIL: {filename} — too small ({fp.stat().st_size} bytes)")
            failures += 1
        else:
            # Quick check: can PIL open it?
            try:
                with Image.open(fp) as test_img:
                    test_img.verify()
            except Exception as e:
                print(f"  FAIL: {filename} — not valid PNG: {e}")
                failures += 1

    if failures == 0:
        print(f"  All {len(answers)} images are valid PNGs >100 bytes [OK]")
    else:
        print(f"  {failures} image(s) failed verification [FAIL]")

    # Verify JSON is valid
    try:
        with open(answers_path, "r", encoding="utf-8") as f:
            reloaded = json.load(f)
        assert reloaded == answers, "JSON round-trip mismatch"
        print(f"  expected_answers.json is valid JSON [OK]")
    except Exception as e:
        print(f"  expected_answers.json validation FAILED: {e} [FAIL]")
        failures += 1

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
