"""
Test Doubao API on Q4 (Taylor) and Q5 (Laurent) from temp/photo.
"""
import sys, time, json, os, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from doubao_api import _load_credentials, _create_client, _encode_image_to_base64

creds = _load_credentials()
client = _create_client(timeout=300)

PHOTO_DIR = Path(__file__).parent.parent / "temp" / "photo"

# Q4 = image index 3 (9017E0B7...), Q5 = image index 4 (93ED634C...)
images = sorted([str(p) for p in PHOTO_DIR.glob("*.*") if p.suffix.lower() in (".jpg",".png",".jpeg")])

def solve_q(img_path, q_label, prompt, sub_count):
    b64 = _encode_image_to_base64(img_path)
    print(f"\n{'='*60}")
    print(f"{q_label}: {os.path.basename(img_path)} ({sub_count}小题)")
    print(f"{'='*60}")
    start = time.time()
    resp = client.chat.completions.create(
        model=creds["model"],
        messages=[{"role":"user","content":[
            {"type":"text","text":prompt},
            {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}
        ]}],
        temperature=0.1,
    )
    elapsed = time.time() - start
    content = resp.choices[0].message.content
    print(f"Time: {elapsed:.1f}s, tokens: prompt={resp.usage.prompt_tokens}, completion={resp.usage.completion_tokens}")
    for line in content.strip().split("\n"):
        print(f"  {line}")
    return content

# Q4: Taylor expansions
q4_prompt = """请解答图片中第12题的所有6个小题。对每个小题：
1. 写出泰勒展开的推导过程（用间接展开法：部分分式+已知级数公式）
2. 给出最终级数表达式（用Σ求和形式）
3. 指出收敛半径R并说明理由（距最近奇点的距离）

逐小题解答，格式清晰。"""

q4_text = solve_q(images[3], "Q4 (Taylor)", q4_prompt, 6)

# Q5: Laurent series
q5_prompt = """请解答图片中第16题的所有7个小题。对每个小题：
1. 用部分分式分解（如需要）
2. 根据指定的圆环域，判断每一项应展开为z的正幂还是负幂
3. 用已知级数公式（如1/(1-ξ)=Σξⁿ）展开
4. 给出最终洛朗级数表达式（用Σ求和形式，标明n的范围）

逐小题解答，格式清晰。"""

q5_text = solve_q(images[4], "Q5 (Laurent)", q5_prompt, 7)

print("\n" + "="*60)
print("DONE — manually compare with reference answers in HANDOFF doc.")
print("="*60)
