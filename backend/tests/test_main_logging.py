import io
import logging

import pytest

from app.main import configure_application_logging


def test_application_debug_logs_use_uvicorn_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO(); handler = logging.StreamHandler(stream)
    monkeypatch.setattr(logging.getLogger("uvicorn"), "handlers", [handler])
    application_logger = logging.getLogger("app")
    monkeypatch.setattr(application_logger, "handlers", [])
    monkeypatch.setattr(application_logger, "propagate", True)
    configure_application_logging("DEBUG")
    logging.getLogger("app.services").debug("submission debug output")
    assert "submission debug output" in stream.getvalue()
