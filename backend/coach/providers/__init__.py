"""Coach providers. :func:`get_provider` picks Gemini or the offline coach."""

from django.conf import settings

from .base import Provider
from .offline import OfflineProvider


def get_provider() -> Provider:
    """Gemini when ``GEMINI_API_KEY`` is set (and the SDK imports), else offline."""
    if getattr(settings, "GEMINI_API_KEY", ""):
        try:
            from .gemini import GeminiProvider
        except ImportError:  # google-genai not installed
            return OfflineProvider()
        return GeminiProvider(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
    return OfflineProvider()


__all__ = ["Provider", "OfflineProvider", "get_provider"]
