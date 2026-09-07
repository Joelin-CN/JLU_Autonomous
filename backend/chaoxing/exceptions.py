"""
Typed exception hierarchy for the Chaoxing automation tool.

All custom exceptions inherit from ChaoxingError, enabling:
    - Catch-all error handling: `except ChaoxingError`
    - Specific recovery strategies: `except AIBackendError as e: if e.retryable: ...`
    - Clean logging with provider/source attribution
"""

from typing import Optional


class ChaoxingError(Exception):
    """Base exception for all Chaoxing automation errors."""
    pass


class ConfigError(ChaoxingError):
    """Configuration-related errors (missing config file, invalid values, missing credentials)."""
    pass


class AuthenticationError(ChaoxingError):
    """Login or credential errors (wrong password, expired session, CAPTCHA during login)."""
    pass


class BrowserError(ChaoxingError):
    """Playwright CLI / browser engine errors (command failure, dead session, timeout)."""
    pass


class NavigationError(BrowserError):
    """Page navigation failures (404, redirect loop, iframe not found)."""
    pass


class QuizSolvingError(ChaoxingError):
    """Quiz solving pipeline errors (all strategies failed, cannot extract questions)."""
    pass


class AIBackendError(ChaoxingError):
    """AI solver backend errors (API failures, rate limiting, timeouts, blocked requests).

    Attributes:
        provider: Human-readable provider name (e.g. "doubao-api").
        retryable: Whether the error is likely transient and worth retrying.

    Recommended usage:
        - Set ``retryable=True`` for transient errors: rate limits, timeouts,
          connection errors — the caller should retry.
        - Leave ``retryable=False`` (the default) for permanent errors: bad
          credentials, invalid model config, blocked requests.
        - Always pass ``provider`` for better logging and recovery decisions.
    """

    def __init__(self, message: str, provider: Optional[str] = None, retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class ContentCompletionError(ChaoxingError):
    """Content bot errors (video playback failed, document scroll stuck, anti-spider detected)."""
    pass


class CaptchaError(ChaoxingError):
    """CAPTCHA detection or solving errors (OCR failed, answer rejected, manual intervention needed)."""
    pass


class FontDecryptError(ChaoxingError):
    """Font decryption pipeline errors (JS injection failed, table not loaded, glyph not found)."""
    pass


class SessionError(ChaoxingError):
    """Session management errors (stale session, zombie process, thread-local corruption)."""
    pass
