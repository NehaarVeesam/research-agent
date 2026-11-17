"""Run records shared by current and future Qwen workflow modules."""
import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class RunArtifacts:
    def __init__(self, root: Path, secrets=()):
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ_") + uuid4().hex[:8]
        self.directory = Path(root) / self.run_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.secrets = tuple(value for value in secrets if value)
        self.lock = threading.Lock()
        self.model_calls = 0
        (self.directory / "model_calls.jsonl").touch()

    @classmethod
    def reopen(cls, directory, secrets=()):
        value = cls.__new__(cls)
        value.directory = Path(directory)
        value.run_id = json.loads((value.directory / "session.json").read_text())["thread_id"]
        value.secrets = tuple(secret for secret in secrets if secret)
        value.lock = threading.Lock()
        value.model_calls = 0  # Set from the request journal by the persistent runner.
        return value

    def redact(self, text):
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        return text

    def write_json(self, name, value):
        destination = self.directory / name
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(self.redact(json.dumps(value, indent=2, ensure_ascii=False)), encoding="utf-8")
        temporary.replace(destination)

    def append_event(self, value):
        with self.lock:
            with (self.directory / "model_calls.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(self.redact(json.dumps(value, ensure_ascii=False)) + "\n")

    def record_model(self, model_call):
        """Retain requests before sending them, so interrupted calls remain visible."""
        def recorded(messages, tools):
            with self.lock:
                self.model_calls += 1
                call_id = self.model_calls
            self.append_event({"event": "request", "call_id": call_id,
                               "at": utc_now(), "messages": messages, "tools": tools})
            try:
                reply = model_call(messages, tools)
            except Exception as exc:
                self.append_event({"event": "error", "call_id": call_id,
                                   "at": utc_now(), "error": str(exc), "type": type(exc).__name__})
                raise
            self.append_event({"event": "response", "call_id": call_id,
                               "at": utc_now(), "reply": reply})
            return reply
        return recorded

    @contextmanager
    def capture_logs(self):
        records = self

        class RedactingFormatter(logging.Formatter):
            def format(self, record):
                return records.redact(super().format(record))

        handler = logging.FileHandler(self.directory / "run.log", encoding="utf-8")
        handler.setFormatter(RedactingFormatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger = logging.getLogger("app.workflow")
        previous_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            yield
        finally:
            logger.removeHandler(handler)
            handler.close()
            logger.setLevel(previous_level)
