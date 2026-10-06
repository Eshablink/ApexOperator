import json
import logging

from apexoperator.observability.logging import JsonFormatter, configure_logging, log_request


def test_json_formatter_emits_structured_fields():
    record = logging.LogRecord("apexoperator", logging.INFO, __file__, 1, "request completed", (), None)
    record.event = "http_request"
    record.method = "GET"
    record.path = "/ready"
    record.status_code = 200
    record.duration_ms = 3.25
    data = json.loads(JsonFormatter().format(record))
    assert data["event"] == "http_request"
    assert data["method"] == "GET"
    assert data["path"] == "/ready"
    assert data["status_code"] == 200
    assert data["duration_ms"] == 3.25


def test_configure_logging_is_idempotent():
    first = configure_logging()
    second = configure_logging()
    assert first is second
    assert len(first.handlers) == 1


def test_log_request_does_not_raise():
    logger = configure_logging()
    log_request(logger, "GET", "/health", 200, 1.2)
