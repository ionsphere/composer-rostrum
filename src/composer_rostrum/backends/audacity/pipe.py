"""Command/response client for Audacity's mod-script-pipe protocol."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from ..base import BackendError


class AudacityPipeError(BackendError):
    pass


def pipe_names() -> tuple[str, str, str]:
    if sys.platform == "win32":
        return (r"\\.\pipe\ToSrvPipe", r"\\.\pipe\FromSrvPipe", "\r\n\0")
    base = "/tmp/audacity_script_pipe."
    return (base + f"to.{os.getuid()}", base + f"from.{os.getuid()}", "\n")


def available() -> bool:
    writing, reading, _ = pipe_names()
    if sys.platform == "win32":
        # Path.exists probes a named pipe by opening it, consuming Audacity's
        # single waiting connection before the real client can attach.
        pipes = set(os.listdir("\\\\.\\pipe\\"))
        return Path(writing).name in pipes and Path(reading).name in pipes
    return Path(writing).exists() and Path(reading).exists()


class AudacityPipe:
    def __init__(self, writer, reader, eol: str):
        self.writer, self.reader, self.eol = writer, reader, eol

    @classmethod
    def connect(cls) -> "AudacityPipe":
        writing, reading, eol = pipe_names()
        try:
            writer = open(writing, "w", encoding="utf-8", newline="")
        except OSError as exc:
            raise AudacityPipeError("Audacity script pipes are unavailable; run Audacity with mod-script-pipe enabled") from exc
        try:
            reader = open(reading, "r", encoding="utf-8", newline="")
        except BaseException:
            writer.close()
            raise
        return cls(writer, reader, eol)

    def close(self) -> None:
        self.reader.close()
        self.writer.close()

    def command(self, value: str) -> str:
        if not value or any(c in value for c in "\r\n\0"):
            raise ValueError("one Audacity command per call is required")
        self.writer.write(value + self.eol)
        self.writer.flush()
        lines = []
        for _ in range(10000):
            line = self.reader.readline()
            if not line:
                raise AudacityPipeError("Audacity closed the response pipe")
            if not line.strip() and lines:
                break
            lines.append(line)
        else:
            raise AudacityPipeError("Audacity response exceeded line budget")
        result = "".join(lines)
        if "BatchCommand finished: OK" not in result:
            raise AudacityPipeError(f"Audacity command failed: {result[-400:]}")
        return result

    def json_info(self, kind: str) -> list[dict]:
        if kind not in {"Tracks", "Clips", "Labels", "Envelopes"}:
            raise ValueError("unsupported Audacity info kind")
        response = self.command(f"GetInfo: Type={kind} Format=JSON")
        start = response.find("[")
        if start < 0:
            raise AudacityPipeError(f"Audacity returned no JSON {kind} data")
        data, _ = json.JSONDecoder().raw_decode(response[start:])
        if not isinstance(data, list):
            raise AudacityPipeError(f"Audacity returned invalid {kind} data")
        return data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
