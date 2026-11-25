import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
run_id_ctx: ContextVar[str | None] = ContextVar("run_id", default=None)

_AUTH_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE)
_QUERY_SECRET_PATTERN = re.compile(
    r"([?&](?:api_key|key|token|secret|password|auth)=)[^&\s]+",
    re.IGNORECASE,
)


def redact_sensitive(text: str) -> str:
    """Redact API keys, bearer tokens, and secret query params from log strings."""
    if not text:
        return text
    settings = get_settings()
    redacted = _AUTH_PATTERN.sub(r"\1[REDACTED]", text)
    redacted = _QUERY_SECRET_PATTERN.sub(r"\1[REDACTED]", redacted)
    for secret in settings.secret_values():
        if secret in redacted:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter with correlation IDs and secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive(record.getMessage()),
        }
        req_id = getattr(record, "request_id", None) or request_id_ctx.get()
        r_id = getattr(record, "run_id", None) or run_id_ctx.get()
        if req_id:
            payload["request_id"] = req_id
        if r_id:
            payload["run_id"] = r_id
        extra_data = getattr(record, "extra_data", None)
        if isinstance(extra_data, dict):
            payload["data"] = {
                k: redact_sensitive(str(v)) if isinstance(v, str) else v
                for k, v in extra_data.items()
            }
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Error"
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
