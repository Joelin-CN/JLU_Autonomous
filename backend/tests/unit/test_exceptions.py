"""Tests for chaoxing.exceptions module."""

from chaoxing.exceptions import (
    ChaoxingError,
    ConfigError,
    AuthenticationError,
    BrowserError,
    NavigationError,
    QuizSolvingError,
    AIBackendError,
    ContentCompletionError,
    CaptchaError,
    FontDecryptError,
    SessionError,
)


class TestExceptionHierarchy:
    """Verify the exception class hierarchy."""

    def test_all_inherit_from_chaoxing_error(self):
        """All custom exceptions should be subclasses of ChaoxingError."""
        exceptions = [
            ConfigError, AuthenticationError, BrowserError,
            NavigationError, QuizSolvingError, AIBackendError,
            ContentCompletionError, CaptchaError, FontDecryptError,
            SessionError,
        ]
        for exc in exceptions:
            assert issubclass(exc, ChaoxingError), f"{exc.__name__} should inherit from ChaoxingError"

    def test_navigation_error_inherits_browser_error(self):
        """NavigationError should be a subclass of BrowserError."""
        assert issubclass(NavigationError, BrowserError)

    def test_ai_backend_error_attributes(self):
        """AIBackendError should support provider and retryable attributes."""
        e = AIBackendError("API timeout", provider="doubao-api", retryable=True)
        assert str(e) == "API timeout"
        assert e.provider == "doubao-api"
        assert e.retryable is True

    def test_ai_backend_error_defaults(self):
        """AIBackendError should have sensible defaults (retryable=False by default for safety)."""
        e = AIBackendError("Rate limited")
        assert e.provider is None
        assert e.retryable is False

    def test_catch_by_base_class(self):
        """All subclasses should be catchable by except ChaoxingError."""
        errors = [
            ConfigError("bad config"),
            AuthenticationError("bad login"),
            BrowserError("browser crash"),
            AIBackendError("timeout"),
        ]
        for err in errors:
            try:
                raise err
            except ChaoxingError:
                pass  # Expected — caught by base class
            except Exception:
                assert False, f"{type(err).__name__} was not caught by ChaoxingError"
