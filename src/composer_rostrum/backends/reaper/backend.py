from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...environment import MusicEnvironment
from ...models import MusicProject
from ..base import (
    BackendCapabilities,
    BackendError,
    DawOperation,
    DawSession,
    NativeProject,
    OperationResult,
    RenderArtifact,
    RenderRequest,
    RenderUnavailableError,
)
from .transport import FileBridgeTransport


class ReaperBackend:
    """Bootstrap REAPER backend with a real protocol-v1 transport seam.

    It creates a deterministic worker bundle and can validate a live bridge
    handshake. Native project mutation/readback/rendering remain intentionally
    disabled until their bridge commands are implemented.
    """

    name = "reaper"
    version = "bootstrap-2"

    # Implemented benchmark capabilities, not aspirational REAPER abilities.
    capabilities = BackendCapabilities()

    target_capabilities = BackendCapabilities(
        midi_notes=True,
        audio_clips=True,
        sampler=True,
        native_synth=True,
        native_eq=True,
        compression=True,
        sidechain=True,
        automation=True,
        offline_render=True,
        readback=True,
        headless_or_unattended=True,
    )

    def materialize(self, project: MusicProject, workspace: Path) -> NativeProject:
        workspace = Path(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "requests").mkdir(exist_ok=True)
        (workspace / "responses").mkdir(exist_ok=True)
        (workspace / "renders").mkdir(exist_ok=True)
        (workspace / "logs").mkdir(exist_ok=True)

        source_path = workspace / "project.music-ir.json"
        source_path.write_text(json.dumps(project.to_dict(), indent=2) + "\n", encoding="utf-8")

        # A real .rpp must be created by REAPER/the bridge, not fabricated by
        # the pure-Python bootstrap with guessed native syntax.
        native_path = workspace / "project.rpp"
        manifest_path = workspace / "reaper-worker.json"
        manifest_path.write_text(json.dumps({
            "backend": self.name,
            "backend_version": self.version,
            "status": "awaiting-reaper-worker",
            "source_music_ir": source_path.name,
            "native_project": native_path.name,
            "bridge_protocol": 1,
            "implemented_capabilities": self.capabilities.to_dict(),
            "target_capabilities": self.target_capabilities.to_dict(),
            "directories": {
                "requests": "requests",
                "responses": "responses",
                "renders": "renders",
                "logs": "logs"
            }
        }, indent=2) + "\n", encoding="utf-8")

        return NativeProject(
            backend=self.name,
            workspace=workspace,
            project_path=native_path,
            manifest_path=manifest_path,
            metadata={"source_music_ir": str(source_path), "bridge_protocol": 1},
        )

    def open(self, native: NativeProject) -> DawSession:
        if native.backend != self.name:
            raise BackendError(f"cannot open {native.backend!r} project with REAPER backend")
        return DawSession(self.name, native, state={
            "connected": False,
            "bridge_protocol": native.metadata.get("bridge_protocol", 1),
        })

    def connect(self, session: DawSession, transport: Any | None = None, timeout: float = 10.0) -> dict[str, Any]:
        if session.closed:
            raise BackendError("DAW session is already closed")
        bridge = transport or FileBridgeTransport(session.native_project.workspace)
        pong = bridge.request("ping", timeout=timeout)
        handshake = bridge.request("capabilities", timeout=timeout)
        if not isinstance(pong, dict) or pong.get("protocol") != 1 or not pong.get("pong"):
            raise BackendError("invalid REAPER bridge ping response")
        if not isinstance(handshake, dict) or handshake.get("protocol") != 1:
            raise BackendError("invalid REAPER bridge capabilities handshake")
        if not isinstance(handshake.get("capabilities"), dict):
            raise BackendError("REAPER bridge handshake omitted capabilities")
        session.state.update({
            "connected": True,
            "transport": bridge,
            "handshake": handshake,
            "live_capabilities": dict(handshake["capabilities"]),
        })
        return handshake

    def create_environment(self, session: DawSession, allowed_tools: list[str]) -> MusicEnvironment:
        self._require_bridge(session)
        raise BackendError("REAPER semantic environment adapter is not implemented yet")

    def commit_environment(self, session: DawSession, environment: MusicEnvironment) -> None:
        self._require_bridge(session)
        raise BackendError("REAPER semantic environment adapter is not implemented yet")

    def execute(self, session: DawSession, operation: DawOperation) -> OperationResult:
        self._require_bridge(session)
        raise BackendError("REAPER semantic command mapping is not implemented yet")

    def readback(self, session: DawSession) -> MusicProject:
        self._require_bridge(session)
        raise BackendError("REAPER readback is not implemented yet")

    def save(self, session: DawSession) -> NativeProject:
        self._require_bridge(session)
        raise BackendError("REAPER save command is not implemented yet")

    def render(self, session: DawSession, request: RenderRequest) -> RenderArtifact:
        self._require_bridge(session)
        raise RenderUnavailableError("REAPER render worker is not implemented yet")

    def close(self, session: DawSession) -> None:
        session.closed = True

    @staticmethod
    def _require_bridge(session: DawSession) -> None:
        if session.closed:
            raise BackendError("DAW session is already closed")
        if not session.state.get("connected"):
            raise BackendError(
                "REAPER worker is not connected; materialization currently creates only the worker bundle"
            )
