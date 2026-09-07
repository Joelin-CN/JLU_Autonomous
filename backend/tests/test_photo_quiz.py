"""
Test Doubao OCR + Solving on temp/photo images.
Phase 1: Doubao OCR extracts text from each image
Phase 2: I solve manually (reference answers)
Phase 3: Doubao solves images directly
Phase 4: Compare accuracy
"""
import sys
import time
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from doubao_api import _load_credentials, _create_client, _encode_image_to_base64

PHOTO_DIR = Path(__file__).parent.parent / "temp" / "photo"
IMAGES = sorted([str(p) for p in PHOTO_DIR.glob("*.*") if p.suffix.lower() in (".jpg", ".png", ".jpeg")])
print(f"Found {len(IMAGES)} images in temp/photo")

creds = _load_credentials()
client = _create_client(timeout=120)

# ═══════════════════════════════════════════════════════════
# PHASE 1: OCR — extract text from each image
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("PHASE 1: Doubao OCR — Extract question text")
print("=" * 60)

ocr_texts = []
for i, img_path in enumerate(IMAGES):
    fname = os.path.basename(img_path)
    b64 = _encode_image_to_base64(img_path)
    print(f"\n[{i+1}/{len(IMAGES)}] OCR: {fname}...")

    start = time.time()
    resp = client.chat.completions.create(
        model=creds["model"],
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "请一字不差地提取图片中的题目文字，包括题目类型（单选题/多选题/判断题）、题目内容、所有选项。不要做任何解答，只提取文字。"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]}],
        temperature=0.1,
    )
    text = resp.choices[0].message.content
    elapsed = time.time() - start
    ocr_texts.append(text)
    print(f"  OCR result ({elapsed:.1f}s):")
    for line in text.strip().split("\n"):
        print(f"    {line}")
    print(f"  [tokens: prompt={resp.usage.prompt_tokens}, completion={resp.usage.completion_tokens}]")

# ═══════════════════════════════════════════════════════════
# PHASE 2: I solve manually (reference answers)
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("PHASE 2: My Manual Solutions (Reference)")
print("=" * 60)

# After seeing the OCR output, I will fill in my answers
# For now, print OCR text so I can read and solve
for i, text in enumerate(ocr_texts):
    print(f"\n--- Q{i+1} ---")
    print(text)

print("\n\n>>> Now I need to read the OCR output above and solve each question...")
print(">>> Waiting for OCR results to be displayed above first.")
