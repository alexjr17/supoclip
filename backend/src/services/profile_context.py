"""
Request/loop-scoped token overrides for publishing services.

Publishing services (YouTube/TikTok) read credentials from the global
``app_settings`` via ``_setting_or_env``. To publish to a per-profile channel,
the API layer / scheduler installs a ``profile_token_context`` that:

- Overrides the setting values the services read (e.g. ``YOUTUBE_REFRESH_TOKEN``).
- Optionally provides a ``sink`` callable so that refreshed tokens (TikTok
  access token renewal) are persisted back to the profile's connected account
  instead of the global app_settings table.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Awaitable, Callable, Dict, Iterator, Optional

ProfileTokenSink = Callable[[Any, Dict[str, str]], Awaitable[None]]

_profile_token_overrides: ContextVar[Optional[Dict[str, str]]] = ContextVar(
    "profile_token_overrides", default=None
)
_profile_token_sink: ContextVar[Optional[ProfileTokenSink]] = ContextVar(
    "profile_token_sink", default=None
)


def get_profile_token_overrides() -> Dict[str, str]:
    return _profile_token_overrides.get() or {}


def get_profile_token_sink() -> Optional[ProfileTokenSink]:
    return _profile_token_sink.get()


@contextmanager
def profile_token_context(
    overrides: Optional[Dict[str, str]] = None,
    sink: Optional[ProfileTokenSink] = None,
) -> Iterator[None]:
    """Install token overrides (and optional persistence sink) for the duration."""
    override_token = _profile_token_overrides.set(overrides or {})
    sink_token = _profile_token_sink.set(sink)
    try:
        yield
    finally:
        _profile_token_overrides.reset(override_token)
        _profile_token_sink.reset(sink_token)
