"""HTTP helpers that never echo secrets."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SECRET_QUERY_KEYS = frozenset({"apikey", "api_key", "token", "password", "secret"})
_SECRET_QUERY_RE = re.compile(
    r"(?i)((?:api[_-]?key|token|password|secret)=)([^&\s]+)"
)


def redact_secrets(text: str) -> str:
    """Replace secret-looking query values in a string."""
    return _SECRET_QUERY_RE.sub(r"\1REDACTED", text)


def sanitize_url(url: str) -> str:
    """Drop secret query params from a URL for logs/errors."""
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _SECRET_QUERY_KEYS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def format_http_error(exc: BaseException) -> str:
    """Status + method + sanitized URL; never include apiKey."""
    response = getattr(exc, "response", None)
    request = getattr(exc, "request", None)
    status = getattr(response, "status_code", None)
    method = getattr(request, "method", None) or ""
    raw_url = ""
    if request is not None:
        raw_url = str(getattr(request, "url", "") or "")
    elif response is not None:
        raw_url = str(getattr(response, "url", "") or "")
    url = sanitize_url(raw_url) if raw_url else ""
    if status is not None:
        return " ".join(p for p in (str(status), method, url) if p)
    return redact_secrets(f"{type(exc).__name__}: {exc}")
