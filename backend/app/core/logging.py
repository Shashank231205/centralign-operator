"""Structured JSON logging with request/run correlation and secret redaction."""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)

_REDACTED = "[REDACTED]"
# key=value / "key": "value" pairs whose key names a secret: keep the key, mask the value.
_SECRET_FIELD = re.compile(
    r"(?i)(\"?(?:authorization|api[_-]?key|password|secret|token)\"?\s*[:=]\s*\"?)[^\s\",}]+"
)
# Bare credentials: bearer tokens and well-known provider key prefixes.
_BARE_SECRETS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._\-]+"),
    re.compile(r"\b(?:gsk|sk|AIza)[A-Za-z0-9_\-]{16,}\b"),
)
_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys() | {"message", "asctime"}
)


def redact(text: str) -> str:
    """Mask anything that looks like a credential before it reaches a log sink."""
    # Bare tokens first: "Authorization: Bearer x" must lose the token, not just the scheme.
    for pattern in _BARE_SECRETS:
        text = pattern.sub(_REDACTED, text)
    return _SECRET_FIELD.sub(rf"\1{_REDACTED}", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_id := request_id_var.get():
            payload["request_id"] = request_id
        if run_id := run_id_var.get():
            payload["run_id"] = run_id
        payload.update(
            {key: value for key, value in record.__dict__.items() if key not in _STANDARD_ATTRS}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, default=str))


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
