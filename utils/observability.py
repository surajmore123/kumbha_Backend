"""
Structured logs that are safe to keep. Everything leaves through `redact`, so a
stray value in a message can't put a token, phone number or position on disk.

Only the route pattern is logged, never the real path: QR tokens and record ids
live in paths, and query strings can hold anything.
"""

import json
import logging
import re
import time
import uuid

_RULES = (
    (re.compile(r"Bearer\s+[\w.\-~+/]+=*", re.I), "Bearer [redacted]"),
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+"), "[jwt]"),
    (
        re.compile(
            r"""(["']?(?:password|passcode|otp|otp_code|code|token|access_token|refresh|secret|api_key|authkey|authorization)["']?\s*[:=]\s*)["']?[^\s"',&}]+""",
            re.I,
        ),
        r"\1[redacted]",
    ),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"(?<![\d.:-])\+?(?:91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?![\d])"), "[phone]"),
    # Decimal degrees to four or more places locate a person.
    (re.compile(r"(?<![\d.])-?\d{1,3}\.\d{4,}(?![\d])"), "[coordinate]"),
)

_EXTRAS = ("request_id", "route", "method", "status", "duration_ms", "task", "error_type", "event")


def redact(text):
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update({key: getattr(record, key) for key in _EXTRAS if hasattr(record, key)})
        if record.exc_info and record.exc_info[0]:
            # The type only: an exception's message can quote user data.
            entry["error_type"] = record.exc_info[0].__name__
        return redact(json.dumps(entry, ensure_ascii=False, default=str))


def logging_config(level="INFO"):
    handler = {"class": "logging.StreamHandler", "formatter": "json"}
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": JsonFormatter}},
        "handlers": {"console": handler},
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            # Django would otherwise log the real path of a failed request.
            "django.request": {"handlers": [], "level": "CRITICAL", "propagate": False},
            "django.server": {"handlers": [], "level": "CRITICAL", "propagate": False},
            "django.db.backends": {"level": "WARNING"},
        },
    }


class RequestLogMiddleware:
    """One line per request, and an id to quote when something goes wrong."""

    logger = logging.getLogger("kumbha.request")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4().hex
        started = time.monotonic()
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        route = match.route if match else "unmatched"
        extra = {
            "request_id": request.request_id,
            "route": route,
            "method": request.method,
            "status": response.status_code,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
        if response.status_code >= 500:
            self.logger.error("Request failed", extra=extra)
        elif not route.startswith(("admin", "static", "health")):
            self.logger.info("Request", extra=extra)
        response["X-Request-ID"] = request.request_id
        return response

    def process_exception(self, request, exception):
        self.logger.error(
            "Unhandled error",
            extra={
                "request_id": getattr(request, "request_id", ""),
                "error_type": type(exception).__name__,
                "event": "api_error",
            },
        )


def log_task_failure(sender=None, exception=None, **_):
    logging.getLogger("kumbha.tasks").error(
        "Task failed",
        extra={
            "task": getattr(sender, "name", "unknown"),
            "error_type": type(exception).__name__,
            "event": "task_failure",
        },
    )
