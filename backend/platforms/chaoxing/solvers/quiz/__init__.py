"""Quiz solving subsystem.

Solves 章节测试 (chapter quizzes) using a 5-tier fallback strategy:
    1. Font decryption → text mode (fastest)
    2. V2 .TiMu container screenshots (element-level)
    3. V1 clip-based screenshots (y-coordinate)
    4. Full-page screenshot
    5. Snapshot text extraction (last resort)
"""
