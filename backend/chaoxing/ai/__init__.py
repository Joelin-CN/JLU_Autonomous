"""AI backend layer — Pluggable quiz-solving AI providers.

Defines the AISolver ABC with concrete implementations:
    - doubao.py: Doubao API via HTTP (OpenAI SDK, sole provider)
    - router.py: Factory function for provider selection
    - prompts.py: Consolidated prompt templates
"""
