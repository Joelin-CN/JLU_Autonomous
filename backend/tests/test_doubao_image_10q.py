"""
Test Doubao API image solving with 10 harder questions.
Generates 10 PNG images, sends via multimodal API, reports results.
"""
import sys
import time
import json
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from doubao_api import doubao_solve_quiz_image

# ── 10 harder quiz questions (probability + statistics) ──
# Each rendered as a separate PNG image

QUESTIONS = [
    # Q1 - Single choice (medium)
    {
        "title": "第1题 [单选题]",
        "stem": "设随机变量 X~N(μ, σ²)，Y~N(μ, σ²)，且 X 与 Y 相互独立，则 D(X-Y) 等于？",
        "options": ["A. 0", "B. σ²", "C. 2σ²", "D. 4σ²"],
    },
    # Q2 - Single choice (hard)
    {
        "title": "第2题 [单选题]",
        "stem": "设 X₁, X₂, ..., Xₙ 是来自总体 N(μ, 1) 的样本，μ 的无偏估计量中方差最小的是？",
        "options": ["A. X₁", "B. (X₁+Xₙ)/2", "C. X̄ (样本均值)", "D. X₁+2X₂"],
    },
    # Q3 - Multi choice (medium)
    {
        "title": "第3题 [多选题]",
        "stem": "关于最大似然估计（MLE），以下哪些说法是正确的？",
        "options": [
            "A. MLE 一定是无偏估计",
            "B. MLE 在大样本下渐近正态",
            "C. MLE 具有相合性（一致性）",
            "D. MLE 可能不是唯一的",
        ],
    },
    # Q4 - Single choice (hard)
    {
        "title": "第4题 [单选题]",
        "stem": "设二维随机变量 (X,Y) 的联合密度为 f(x,y)=2, 0<x<y<1。则 P(X<0.5 | Y=0.8) 约为？",
        "options": ["A. 0.375", "B. 0.500", "C. 0.625", "D. 0.750"],
    },
    # Q5 - True/False (medium, tricky)
    {
        "title": "第5题 [判断题]",
        "stem": "设总体 X~N(μ,σ²)，σ² 未知。假设检验 H₀: μ=μ₀ vs H₁: μ≠μ₀，当样本量 n→∞ 时，即使 μ 的真实值与 μ₀ 相差极小，检验也最终会拒绝 H₀。",
        "options": ["正确", "错误"],
    },
    # Q6 - Single choice (hard - Bayes)
    {
        "title": "第6题 [单选题]",
        "stem": "某罕见病发病率 0.1%，检测方法灵敏度 99%，特异度 99%。某人检测为阳性，其真正患病的概率约为？",
        "options": ["A. 约 1%", "B. 约 9%", "C. 约 50%", "D. 约 99%"],
    },
    # Q7 - Single choice (medium)
    {
        "title": "第7题 [单选题]",
        "stem": "设 X 服从参数 λ 的泊松分布，已知 P(X=1)=P(X=2)，则 λ 等于？",
        "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
    },
    # Q8 - Multi choice (hard)
    {
        "title": "第8题 [多选题]",
        "stem": "关于假设检验的 p 值，以下哪些说法是正确的？",
        "options": [
            "A. p 值越小，拒绝 H₀ 的证据越强",
            "B. p 值是在 H₀ 为真的条件下，观察到的检验统计量更极端的概率",
            "C. 当 p 值 < α 时拒绝 H₀",
            "D. p 值等于 H₀ 为真的概率",
        ],
    },
    # Q9 - Single choice (hard - convergence)
    {
        "title": "第9题 [单选题]",
        "stem": "设 X₁,...,Xₙ i.i.d. ~ U(0,θ)。θ 的矩估计量为 2X̄，其均方误差 MSE 在 n→∞ 时的收敛阶为？",
        "options": ["A. O(1/n)", "B. O(1/√n)", "C. O(1/n²)", "D. O(log n / n)"],
    },
    # Q10 - True/False (hard - conceptual)
    {
        "title": "第10题 [判断题]",
        "stem": "中心极限定理要求样本来自正态总体，否则样本均值的分布不会趋近于正态分布。",
        "options": ["正确", "错误"],
    },
]


def create_question_image(q: dict, idx: int) -> str:
    """Draw one question as a PNG and return the path."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 320), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Load CJK font
    font = None
    for fp in [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 22)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()

    # Draw title
    y = 15
    draw.text((20, y), q["title"], fill=(0, 0, 0), font=font)
    y += 35

    # Draw stem (wrap long text)
    stem = q["stem"]
    max_chars_per_line = 38
    while len(stem) > max_chars_per_line:
        cut = stem[:max_chars_per_line]
        draw.text((30, y), cut, fill=(0, 0, 0), font=font)
        stem = stem[max_chars_per_line:]
        y += 30
    draw.text((30, y), stem, fill=(0, 0, 0), font=font)
    y += 40

    # Draw options
    for opt in q["options"]:
        draw.text((50, y), opt, fill=(0, 0, 0), font=font)
        y += 30

    path = os.path.join(tempfile.gettempdir(), f"_doubao_10q_q{idx+1}.png")
    img.save(path, "PNG")
    return path


def main():
    print("=" * 60)
    print("DOUBAO API — 10 HARD QUESTIONS IMAGE TEST")
    print("=" * 60)

    # ── Generate images ──
    print("\n[1] Generating 10 question images...")
    paths = []
    for i, q in enumerate(QUESTIONS):
        p = create_question_image(q, i)
        size_kb = os.path.getsize(p) / 1024
        paths.append(p)
        print(f"  Q{i+1}: {os.path.basename(p)} ({size_kb:.1f} KB) — {q['title']}")

    total_size_kb = sum(os.path.getsize(p) for p in paths) / 1024
    print(f"\n  Total: {len(paths)} images, {total_size_kb:.1f} KB")

    # ── Send to Doubao ──
    print(f"\n[2] Sending 10 images to Doubao API (multimodal)...")
    print(f"    Course: 概率论与数理统计")
    print(f"    Section: 综合难题测试(10题)")
    print()

    start = time.time()
    try:
        answers = doubao_solve_quiz_image(
            paths,
            "概率论与数理统计",
            "综合难题测试"
        )
        elapsed = time.time() - start
        print(f"\n[3] Done! Response time: {elapsed:.1f}s")
        print(f"    Answers received: {len(answers)}/10")

        # ── Display answers ──
        print(f"\n{'─' * 50}")
        print(f"{'题号':<8}{'答案':<25}{'类型'}")
        print(f"{'─' * 50}")
        for a in answers:
            idx = a.get("index", "?")
            ans = a.get("answer", "?")
            ans_str = json.dumps(ans, ensure_ascii=False)
            # Determine type
            if isinstance(ans, list):
                qtype = "多选"
            elif isinstance(ans, str) and ans in ("正确", "错误"):
                qtype = "判断"
            elif isinstance(ans, str) and len(ans) == 1 and ans.isalpha():
                qtype = "单选"
            else:
                qtype = "其他"
            print(f"  Q{idx:<6}{ans_str:<25}{qtype}")

        # ── Check expected answers ──
        expected = {
            1: "C",           # D(X-Y) = D(X) + D(Y) = 2σ²
            2: "C",           # Sample mean is UMVUE
            3: ["B", "C", "D"],  # MLE properties
            4: "C",           # Conditional probability
            5: "正确",         # Consistency of hypothesis test
            6: "B",           # Bayes theorem: ~9%
            7: "B",           # Poisson: λ=2
            8: ["A", "B", "C"],  # p-value properties
            9: "A",           # MSE convergence O(1/n)
            10: "错误",        # CLT doesn't require normality
        }
        correct = 0
        checked = 0
        print(f"\n{'─' * 50}")
        print(f"正确性检查（与标准答案对比）：")
        print(f"{'─' * 50}")
        for a in answers:
            idx = a.get("index")
            ans = a.get("answer")
            exp = expected.get(idx)
            if exp is not None:
                checked += 1
                # Compare: handle both single and multi-select
                if isinstance(exp, list) and isinstance(ans, list):
                    is_correct = set(ans) == set(exp)
                else:
                    is_correct = (str(ans).strip() == str(exp).strip())
                if is_correct:
                    correct += 1
                    print(f"  Q{idx}: ✓ {json.dumps(ans, ensure_ascii=False)} == {json.dumps(exp, ensure_ascii=False)}")
                else:
                    print(f"  Q{idx}: ✗ {json.dumps(ans, ensure_ascii=False)} != {json.dumps(exp, ensure_ascii=False)}")

        accuracy = correct / max(checked, 1) * 100
        print(f"\n  正确率: {correct}/{checked} = {accuracy:.0f}%")

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
    finally:
        # Clean up
        for p in paths:
            try:
                os.unlink(p)
            except Exception:
                pass
        print(f"\n  已清理 {len(paths)} 个临时图片文件")


if __name__ == "__main__":
    main()
