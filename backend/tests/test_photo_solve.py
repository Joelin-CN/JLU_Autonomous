"""
Phase 3-4: Doubao image solving + accuracy comparison.
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

creds = _load_credentials()
client = _create_client(timeout=300)

# ═══════════════════════════════════════════════════════════
# MY REFERENCE ANSWERS (手工解答)
# ═══════════════════════════════════════════════════════════

MY_ANSWERS = {
    # Q1: ∮_C dz/((z²+1)(z²+4)), C:|z|=3/2
    # Poles inside C (|z|<1.5): z=±i (|z|=1)
    # Res(z=i) = 1/((z+i)(z²+4))|_{z=i} = 1/(2i·3) = 1/(6i)
    # Res(z=-i) = 1/((z-i)(z²+4))|_{z=-i} = 1/(-2i·3) = -1/(6i)
    # Sum = 0, Answer = 0
    1: {
        "question": "∮_C dz/((z²+1)(z²+4)), C:|z|=3/2",
        "answer": "0",
        "explanation": "奇点z=±i在C内(|z|=1<1.5), z=±2i在C外。Res(z=i)=1/(6i), Res(z=-i)=-1/(6i), 和=0, 积分=2πi·0=0",
    },
    # Q2: ∮_C e^z/(z-a)³ dz, C:|z|=1, |a|≠1
    # If |a|<1: use Cauchy integral formula f''(a)/2! = (1/2πi)∮ f(z)/(z-a)³
    # f(z)=e^z, f''(z)=e^z, Answer = 2πi·e^a/2 = πi·e^a
    # If |a|>1: integrand analytic inside C, Answer = 0
    2: {
        "question": "∮_C e^z/(z-a)³ dz, C:|z|=1, |a|≠1",
        "answer": "|a|<1时为πi·eᵃ; |a|>1时为0",
        "explanation": "|a|<1: Cauchy积分公式, f''(a)/2!=e^a/2, 积分=2πi·e^a/2=πie^a。|a|>1: 被积函数在C内解析, 积分=0",
    },
}

print("=" * 60)
print("MY REFERENCE ANSWERS (手工解答)")
print("=" * 60)
for qid, ans in MY_ANSWERS.items():
    print(f"\nQ{qid}: {ans['question']}")
    print(f"  答案: {ans['answer']}")
    print(f"  解释: {ans['explanation']}")

# ═══════════════════════════════════════════════════════════
# PHASE 3: Doubao solves each image directly
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("PHASE 3: Doubao Image Solving")
print("=" * 60)

doubao_answers = {}

# Q1 and Q2 (has definitive answer)
for i in [0, 1]:  # Q1=index 0, Q2=index 1
    img_path = IMAGES[i]
    fname = os.path.basename(img_path)
    b64 = _encode_image_to_base64(img_path)
    qid = i + 1

    prompt = """请解答图片中的复变函数积分题目。
要求：
1. 先判断被积函数在积分围道内有哪些奇点
2. 计算每个奇点的留数
3. 用留数定理得出结果
4. 最后用一行单独给出最终答案，格式为 "答案: (你的答案)"
"""
    print(f"\n[Q{qid}] {fname}")
    start = time.time()
    resp = client.chat.completions.create(
        model=creds["model"],
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]}],
        temperature=0.1,
    )
    elapsed = time.time() - start
    content = resp.choices[0].message.content
    doubao_answers[qid] = content
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Tokens: prompt={resp.usage.prompt_tokens}, completion={resp.usage.completion_tokens}")
    print(f"  Answer:")
    for line in content.strip().split("\n"):
        print(f"    {line}")

# Q3 (multi-part: find analytic function — sample 1 sub-problem)
print(f"\n[Q3] {os.path.basename(IMAGES[2])}")
print("  (多子题，抽样检查第1小题)")
b64 = _encode_image_to_base64(IMAGES[2])
start = time.time()
resp = client.chat.completions.create(
    model=creds["model"],
    messages=[{"role": "user", "content": [
        {"type": "text", "text": "图片中有4个小题。只做第1小题：已知调和函数 u=(x-y)(x²+4xy+y²)，求解析函数 f(z)=u+iv。用C-R方程法逐步推导，给出最终f(z)表达式。"},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
    ]}],
    temperature=0.1,
)
elapsed = time.time() - start
print(f"  Time: {elapsed:.1f}s, Tokens: prompt={resp.usage.prompt_tokens}, completion={resp.usage.completion_tokens}")
for line in resp.choices[0].message.content.strip().split("\n"):
    print(f"    {line}")

# ═══════════════════════════════════════════════════════════
# PHASE 4: Accuracy Comparison
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("PHASE 4: Accuracy Comparison")
print("=" * 60)

# Compare Q1
print("\n--- Q1: Contour integral ---")
q1_text = doubao_answers.get(1, "")
q1_correct = False
if "0" in q1_text.split("答案:")[-1].strip() if "答案:" in q1_text else False:
    q1_correct = True
# More thorough check: look for answer=0 anywhere near the end
import re
q1_final = q1_text.split("答案:")[-1].strip() if "答案:" in q1_text else q1_text[-200:]
q1_match = re.search(r'(?:答案|结果|积分)\s*[=:：]\s*(\S+)', q1_text[-300:])
if q1_match:
    q1_doubao_ans = q1_match.group(1).strip()
else:
    q1_doubao_ans = q1_final[:50]
print(f"  Doubao answer: {q1_doubao_ans}")
print(f"  Reference:     0")
# Check if answer contains 0
q1_is_zero = bool(re.search(r'(?:^|[=\s:：])\s*0\s*$', q1_doubao_ans)) or "0" in q1_doubao_ans.replace(" ", "")
print(f"  Result: {'CORRECT' if q1_is_zero else 'WRONG — need manual check'}")

# Compare Q2
print("\n--- Q2: e^z/(z-a)³ ---")
q2_text = doubao_answers.get(2, "")
q2_final = q2_text.split("答案:")[-1].strip() if "答案:" in q2_text else q2_text[-300:]
q2_match = re.search(r'(?:答案|结果|积分)\s*[=:：]\s*(.+?)(?:\n|$)', q2_text[-500:])
if q2_match:
    q2_doubao_ans = q2_match.group(1).strip()
else:
    q2_doubao_ans = q2_final[:80]
print(f"  Doubao answer: {q2_doubao_ans}")
print(f"  Reference:     |a|<1时为πi·eᵃ; |a|>1时为0")
# Check key patterns
has_pi_i_e_a = bool(re.search(r'π\s*i|pi\s*i|\bπi\b', q2_doubao_ans))
has_zero = "0" in q2_doubao_ans
has_condition = bool(re.search(r'\|a\||<1|>1|内|外', q2_doubao_ans))
print(f"  Has πie^a: {has_pi_i_e_a}, Has 0: {has_zero}, Has condition: {has_condition}")
if has_pi_i_e_a and has_zero and has_condition:
    print(f"  Result: CORRECT")
elif has_zero and has_condition:
    print(f"  Result: PARTIALLY CORRECT (may be missing πie^a case)")
else:
    print(f"  Result: NEEDS MANUAL REVIEW — read the full answer above")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  Q1: {'CORRECT' if q1_is_zero else 'NEEDS REVIEW'}")
print(f"  Q2: {'CORRECT' if (has_pi_i_e_a and has_zero and has_condition) else 'NEEDS REVIEW'}")
print(f"  Q3-Q5: Multi-part derivation problems — manually check the output above")
