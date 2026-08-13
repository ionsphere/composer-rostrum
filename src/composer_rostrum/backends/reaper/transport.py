from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..base import BackendError


@dataclass(frozen=True)
class BridgeResponse:
    request_id: str
    ok: bool
    result: Any
    error: dict[str, Any] | None


class FileBridgeTransport:
    """Debuggable protocol-v1 request/response transport for a REAPER worker."""

    protocol = 1

    def __init__(self, workspace: Path, poll_interval: float = 0.02):
        self.workspace = Path(workspace)
        self.requests_dir = self.workspace / "requests"
        self.responses_dir = self.workspace / "responses"
        self.requests_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir.mkdir(parents=True, exist_ok=True)
        self.poll_interval = float(poll_interval)
        self._next_id = self._discover_next_id()

    def prepare_request(self, command: str, arguments: dict[str, Any] | None = None) -> tuple[str, Path]:
        request_id = f"{self._next_id:06d}"
        self._next_id += 1
        envelope = {
            "protocol": self.protocol,
            "id": request_id,
            "command": str(command),
            "arguments": arguments or {},
        }
        final_path = self.requests_dir / f"{request_id}.json"
        temporary = self.requests_dir / f".{request_id}.{os.getpid()}.tmp"
        temporary.write_text(json.dumps(envelope, separators=(",", ":")) + "\n", encoding="utf-8")
        temporary.replace(final_path)
        return request_id, final_path

    def await_response(self, request_id: str, timeout: float = 10.0) -> BridgeResponse:
        path = self.responses_dir / f"{request_id}.json"
        deadline = time.monotonic() + float(timeout)
        while time.monotonic() < deadline:
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("protocol") != self.protocol:
                    raise BackendError("REAPER bridge returned an incompatible protocol version")
                if str(payload.get("id")) != str(request_id):
                    raise BackendError("REAPER bridge response ID does not match request ID")
                return BridgeResponse(
                    request_id=str(request_id),
                    ok=bool(payload.get("ok")),
                    result=payload.get("result"),
                    error=payload.get("error"),
                )
            time.sleep(self.poll_interval)
        raise BackendError(f"timed out waiting for REAPER bridge response {request_id}")

    def request(self, command: str, arguments: dict[str, Any] | None = None, timeout: float = 10.0) -> Any:
        request_id, _ = self.prepare_request(command, arguments)
        response = self.await_response(request_id, timeout=timeout)
        if not response.ok:
            detail = response.error or {"kind": "unknown", "message": "bridge command failed"}
            raise BackendError(f"REAPER bridge {detail.get('kind')}: {detail.get('message')}")
        return response.result

    def _discover_next_id(self) -> int:
        ids = []
        for directory in (self.requests_dir, self.responses_dir):
            for path in directory.glob("*.json"):
                try:
                    ids.append(int(path.stem))
                except ValueError:
                    continue
        return max(ids, default=0) + 1
