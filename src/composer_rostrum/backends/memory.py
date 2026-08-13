from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from ..environment import MusicEnvironment
from ..models import MusicProject
from .base import (
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


class InMemoryBackend:
    """Reference backend for semantic benchmark execution.

    It persists Music IR in a workspace so its lifecycle matches real backends,
    but it intentionally does not pretend to produce audio.
    """

    name = "memory"
    version = "1"
    capabilities = BackendCapabilities(
        midi_notes=True,
        audio_clips=True,
        sampler=True,
        automation=False,
        offline_render=False,
        readback=True,
        headless_or_unattended=True,
    )

    def materialize(self, project: MusicProject, workspace: Path) -> NativeProject:
        workspace = Path(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        project_path = workspace / "project.music-ir.json"
        project_path.write_text(json.dumps(project.to_dict(), indent=2) + "\n", encoding="utf-8")
        manifest_path = workspace / "backend-manifest.json"
        manifest_path.write_text(json.dumps({
            "backend": self.name,
            "version": self.version,
            "capabilities": self.capabilities.to_dict(),
        }, indent=2) + "\n", encoding="utf-8")
        return NativeProject(self.name, workspace, project_path, manifest_path)

    def open(self, native: NativeProject) -> DawSession:
        if native.backend != self.name:
            raise BackendError(f"cannot open {native.backend!r} project with {self.name!r} backend")
        data = json.loads(native.project_path.read_text(encoding="utf-8"))
        return DawSession(self.name, native, state={"project": MusicProject.from_dict(data)})

    def create_environment(self, session: DawSession, allowed_tools: list[str]) -> MusicEnvironment:
        self._assert_open(session)
        return MusicEnvironment(deepcopy(session.state["project"]), allowed_tools)

    def commit_environment(self, session: DawSession, environment: MusicEnvironment) -> None:
        self._assert_open(session)
        session.state["project"] = environment.project

    def execute(self, session: DawSession, operation: DawOperation) -> OperationResult:
        self._assert_open(session)
        environment = MusicEnvironment(session.state["project"], [operation.name])
        result = environment.call(operation.name, **operation.arguments)
        changed = environment.project.to_dict() != session.state["project"].to_dict()
        session.state["project"] = environment.project
        return OperationResult(operation.name, result, changed)

    def readback(self, session: DawSession) -> MusicProject:
        self._assert_open(session)
        return deepcopy(session.state["project"])

    def save(self, session: DawSession) -> NativeProject:
        self._assert_open(session)
        session.native_project.project_path.write_text(
            json.dumps(session.state["project"].to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        return session.native_project

    def render(self, session: DawSession, request: RenderRequest) -> RenderArtifact:
        self._assert_open(session)
        raise RenderUnavailableError(
            "the in-memory backend does not render audio; use a render-capable DAW backend"
        )

    def close(self, session: DawSession) -> None:
        session.closed = True

    @staticmethod
    def _assert_open(session: DawSession) -> None:
        if session.closed:
            raise BackendError("DAW session is already closed")
