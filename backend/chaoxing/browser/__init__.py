"""Browser abstraction layer — Playwright CLI wrapper.

Provides the low-level interface to playwright-cli:
    - engine.py: pw(), pw_snapshot(), pw_click(), pw_goto(), pw_fill()
    - js_runner.py: JS injection via temp files
    - viewport.py: Viewport size management
"""
