from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..models import MusicProject


class BackendError(RuntimeError):
    """Base class for DAW backend/infrastructure failures."""


class CapabilityError(BackendError):
    """Raised when a task requires a semantic capability the backend lacks."""


class RenderUnavailableError(BackendError):
    """Raised when a backend/session cannot produce a genuine audio render."""


@dataclass(frozen=True)
class BackendCapabilities:
    midi_notes: bool = False
    audio_clips: bool = False
    sampler: bool = False
    native_synth: bool = False
    native_eq: bool = False
    compression: bool = False
    sidechain: bool = False
    automation: bool = False
    offline_render: bool = False
    readback: bool = False
    headless_or_unattended: bool = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)

    def require(self, names: list[str]) -> None:
        missing = [name for name in names if not getattr(self, name, False)]
        if missing:
            raise CapabilityError(f"backend is missing required capabilities: {', '.join(missing)}")


@dataclass(frozen=True)
class NativeProject:
    backend: str
    workspace: Path
    project_path: Path
    manifest_path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DawSession:
    backend: str
    native_project: NativeProject
    state: dict[str, Any] = field(default_factory=dict)
    closed: bool = False


@dataclass(frozen=True)
class DawOperation:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OperationResult:
    operation: str
    result: Any = None
    changed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RenderRequest:
    scope: str = "project"
    start: float | None = None
    end: float | None = None
    sample_rate: int = 48000
    channels: int = 2
    format: str = "wav"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RenderArtifact:
    render_id: str
    backend: str
    project_hash: str
    path: Path
    content_hash: str
    request: RenderRequest
    duration_seconds: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        return data


class DawBackend(Protocol):
    name: str
    version: str
    capabilities: BackendCapabilities

    def materialize(self, project: MusicProject, workspace: Path) -> NativeProject:
        ...

    def open(self, native: NativeProject) -> DawSession:
        ...

    def execute(self, session: DawSession, operation: DawOperation) -> OperationResult:
        ...

    def readback(self, session: DawSession) -> MusicProject:
        ...

    def save(self, session: DawSession) -> NativeProject:
        ...

    def render(self, session: DawSession, request: RenderRequest) -> RenderArtifact:
        ...

    def close(self, session: DawSession) -> None:
        ...
