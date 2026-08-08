from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from .models import MusicProject


class ToolError(RuntimeError):
    """Raised when an agent attempts an unavailable or invalid environment action."""


@dataclass
class TrajectoryEvent:
    index: int
    tool: str
    arguments: dict[str, Any]
    result: Any
    before_hash: str
    after_hash: str
    changed_paths: list[str]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def project_hash(project: MusicProject) -> str:
    payload = json.dumps(project.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _diff_paths(before: Any, after: Any, prefix: str = "") -> list[str]:
    if type(before) is not type(after):
        return [prefix or "$root"]
    if isinstance(before, dict):
        paths: list[str] = []
        for key in sorted(set(before) | set(after)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in before or key not in after:
                paths.append(path)
            else:
                paths.extend(_diff_paths(before[key], after[key], path))
        return paths
    if isinstance(before, list):
        paths = []
        for index in range(max(len(before), len(after))):
            path = f"{prefix}.{index}" if prefix else str(index)
            if index >= len(before) or index >= len(after):
                paths.append(path)
            else:
                paths.extend(_diff_paths(before[index], after[index], path))
        return paths
    return [] if before == after else [prefix or "$root"]


class MusicEnvironment:
    """Owns mutable project state and exposes the benchmark's bounded tool surface.

    Agents receive this object rather than the MusicProject itself. The public
    project property returns a deep copy so an adapter cannot mutate benchmark
    state without going through a logged tool call.
    """

    def __init__(self, project: MusicProject, allowed_tools: list[str]):
        self._project = deepcopy(project)
        self.allowed_tools = frozenset(allowed_tools)
        self.trajectory: list[TrajectoryEvent] = []

    @property
    def project(self) -> MusicProject:
        return deepcopy(self._project)

    def call(self, tool: str, **arguments: Any) -> Any:
        if tool not in self.allowed_tools:
            raise ToolError(f"tool {tool!r} is not allowed for this task")

        handler = getattr(self, f"_tool_{tool}", None)
        if handler is None:
            raise ToolError(f"tool {tool!r} is not implemented")

        before = deepcopy(self._project)
        before_hash = project_hash(before)
        try:
            result = handler(**arguments)
        except Exception as exc:
            after_hash = project_hash(self._project)
            self.trajectory.append(TrajectoryEvent(
                index=len(self.trajectory),
                tool=tool,
                arguments=deepcopy(arguments),
                result=None,
                before_hash=before_hash,
                after_hash=after_hash,
                changed_paths=_diff_paths(before.to_dict(), self._project.to_dict()),
                error=f"{type(exc).__name__}: {exc}",
            ))
            raise

        after_hash = project_hash(self._project)
        self.trajectory.append(TrajectoryEvent(
            index=len(self.trajectory),
            tool=tool,
            arguments=deepcopy(arguments),
            result=deepcopy(result),
            before_hash=before_hash,
            after_hash=after_hash,
            changed_paths=_diff_paths(before.to_dict(), self._project.to_dict()),
        ))
        return deepcopy(result)

    def _tool_inspect_project(self, path: str | None = None) -> Any:
        value: Any = self._project.to_dict()
        if path is None:
            return value
        for part in path.split("."):
            if isinstance(value, dict):
                value = value[part]
            elif isinstance(value, list):
                value = value[int(part)]
            else:
                raise ToolError(f"cannot descend through {path!r}")
        return value

    def _tool_set_tempo(self, bpm: float) -> dict[str, float]:
        bpm = float(bpm)
        if bpm <= 0:
            raise ToolError("tempo must be greater than zero")
        self._project.tempo = bpm
        return {"tempo": bpm}

    def _tool_set_key(self, key: str | None) -> dict[str, str | None]:
        self._project.key = key
        return {"key": key}

    def _tool_set_meter(self, meter: str) -> dict[str, str]:
        if "/" not in meter:
            raise ToolError("meter must look like '4/4'")
        numerator, denominator = meter.split("/", 1)
        if not numerator.isdigit() or not denominator.isdigit() or int(numerator) <= 0 or int(denominator) <= 0:
            raise ToolError("meter must contain positive integer numerator and denominator")
        self._project.meter = meter
        return {"meter": meter}

    def _find_track(self, track_id: str) -> dict[str, Any]:
        for track in self._project.tracks:
            if track.get("id") == track_id:
                return track
        raise ToolError(f"track {track_id!r} was not found")

    def _tool_mute_track(self, track_id: str, muted: bool = True) -> dict[str, Any]:
        track = self._find_track(track_id)
        track["muted"] = bool(muted)
        return {"track_id": track_id, "muted": bool(muted)}

    def _tool_rename_track(self, track_id: str, name: str) -> dict[str, str]:
        track = self._find_track(track_id)
        track["name"] = str(name)
        return {"track_id": track_id, "name": str(name)}

    def _tool_set_track_gain(self, track_id: str, gain_db: float) -> dict[str, Any]:
        track = self._find_track(track_id)
        track["gain_db"] = float(gain_db)
        return {"track_id": track_id, "gain_db": float(gain_db)}
