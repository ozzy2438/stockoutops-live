"""Loopback HTTP receiver for local webhook delivery proofs. No public internet."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class RecordingWebhookServer:
    def __init__(
        self,
        *,
        hang_seconds: float = 0,
        status: int = 200,
        status_sequence: list[int] | None = None,
    ) -> None:
        self.hang_seconds = hang_seconds
        self.status = status
        self.status_sequence = deque(status_sequence or [])
        self.requests: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/alerts"

    def start(self) -> RecordingWebhookServer:
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def __enter__(self) -> RecordingWebhookServer:
        return self.start()

    def __exit__(self, *args: object) -> None:
        self.stop()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                with outer.lock:
                    if outer.status_sequence:
                        status = outer.status_sequence.popleft()
                    else:
                        status = outer.status
                    outer.requests.append(
                        {
                            "path": self.path,
                            "authorization": self.headers.get("Authorization"),
                            "idempotency_key": self.headers.get("Idempotency-Key"),
                            "content_type": self.headers.get("Content-Type"),
                            "body": json.loads(body.decode("utf-8")) if body else None,
                        }
                    )
                if outer.hang_seconds > 0:
                    time.sleep(outer.hang_seconds)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler
