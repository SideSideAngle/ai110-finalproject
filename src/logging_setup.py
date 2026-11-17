"""Logging: a human-readable app.log plus a machine-readable events.jsonl."""
import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler

LOG_DIR = os.environ.get("RECOMMENDER_LOG_DIR", "logs")
_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Idempotent. Writes logs/app.log (rotating); errors also go to the console."""
    global _configured
    if _configured:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(os.path.join(LOG_DIR, "app.log"),
                                       maxBytes=512_000, backupCount=2, encoding="utf-8")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setLevel(logging.ERROR)
    console.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console)
    _configured = True


REDACTED_FIELDS = ("request", "note")


def log_event(kind: str, **fields) -> None:
    """Append one JSON line (request, fallback, feedback, ...) to logs/events.jsonl.

    With LOG_REQUEST_TEXT=0 (the web app's default) what users typed is replaced by
    "[redacted]", so a hosted site does not store visitors' text.
    """
    if os.environ.get("LOG_REQUEST_TEXT", "1") == "0":
        fields = {k: ("[redacted]" if k in REDACTED_FIELDS else v) for k, v in fields.items()}
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, **fields}
        with open(os.path.join(LOG_DIR, "events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError:
        logging.getLogger(__name__).exception("Could not write event log")
