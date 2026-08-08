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
        paths: list[str] = []
        for index in range(max(len(before), len(after))):
            path = f"{prefix}.{index}" if prefix else str(index)
            if index >= len(before) or index >= len(after):
                paths.append(path)
            else:
                paths.extend(_diff_paths(before[index], after[index], path))
        return paths
    return [] if before == after else [prefix or "$root"]


class MusicEnvironment:
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
            self.trajectory.append(TrajectoryEvent(len(self.trajectory), tool, deepcopy(arguments), None,
                before_hash, project_hash(self._project), _diff_paths(before.to_dict(), self._project.to_dict()),
                f"{type(exc).__name__}: {exc}"))
            raise
        self.trajectory.append(TrajectoryEvent(len(self.trajectory), tool, deepcopy(arguments), deepcopy(result),
            before_hash, project_hash(self._project), _diff_paths(before.to_dict(), self._project.to_dict())))
        return deepcopy(result)

    def _tool_inspect_project(self, path: str | None = None) -> Any:
        value: Any = self._project.to_dict()
        if path is None:
            return value
        for part in path.split("."):
            value = value[int(part)] if isinstance(value, list) else value[part]
        return value

    def _find_track(self, track_id: str) -> dict[str, Any]:
        for track in self._project.tracks:
            if track.get("id") == track_id:
                return track
        raise ToolError(f"track {track_id!r} was not found")

    def _find_asset(self, asset_id: str) -> dict[str, Any]:
        for asset in self._project.assets:
            if asset.get("id") == asset_id:
                return asset
        raise ToolError(f"asset {asset_id!r} was not found")

    def _find_clip(self, track_id: str, clip_id: str) -> dict[str, Any]:
        track = self._find_track(track_id)
        for clip in track.get("clips", []):
            if clip.get("id") == clip_id:
                return clip
        raise ToolError(f"clip {clip_id!r} was not found on track {track_id!r}")

    def _tool_set_tempo(self, bpm: float) -> dict[str, float]:
        bpm = float(bpm)
        if bpm <= 0: raise ToolError("tempo must be greater than zero")
        self._project.tempo = bpm
        return {"tempo": bpm}

    def _tool_set_key(self, key: str | None) -> dict[str, str | None]:
        self._project.key = key
        return {"key": key}

    def _tool_set_meter(self, meter: str) -> dict[str, str]:
        if "/" not in meter: raise ToolError("meter must look like '4/4'")
        self._project.meter = meter
        return {"meter": meter}

    def _tool_mute_track(self, track_id: str, muted: bool = True) -> dict[str, Any]:
        track = self._find_track(track_id); track["muted"] = bool(muted)
        return {"track_id": track_id, "muted": bool(muted)}

    def _tool_rename_track(self, track_id: str, name: str) -> dict[str, str]:
        track = self._find_track(track_id); track["name"] = str(name)
        return {"track_id": track_id, "name": str(name)}

    def _tool_set_track_gain(self, track_id: str, gain_db: float) -> dict[str, Any]:
        track = self._find_track(track_id); track["gain_db"] = float(gain_db)
        return {"track_id": track_id, "gain_db": float(gain_db)}

    def _tool_trim_clip(self, track_id: str, clip_id: str, source_start: float, source_end: float) -> dict[str, Any]:
        clip = self._find_clip(track_id, clip_id)
        if source_start < 0 or source_end <= source_start: raise ToolError("invalid source range")
        asset = self._find_asset(clip["asset_id"])
        if source_end > float(asset["duration_seconds"]): raise ToolError("trim exceeds source asset")
        clip["source_start"] = float(source_start); clip["source_end"] = float(source_end)
        return {"track_id": track_id, "clip_id": clip_id, "source_start": float(source_start), "source_end": float(source_end)}

    def _tool_set_clip_pitch(self, track_id: str, clip_id: str, semitones: float) -> dict[str, Any]:
        clip = self._find_clip(track_id, clip_id); clip["pitch_semitones"] = float(semitones)
        return {"track_id": track_id, "clip_id": clip_id, "pitch_semitones": float(semitones)}

    def _tool_stretch_clip(self, track_id: str, clip_id: str, ratio: float) -> dict[str, Any]:
        ratio = float(ratio)
        if ratio <= 0: raise ToolError("stretch ratio must be greater than zero")
        clip = self._find_clip(track_id, clip_id); clip["stretch_ratio"] = ratio
        return {"track_id": track_id, "clip_id": clip_id, "stretch_ratio": ratio}

    def _tool_reverse_clip(self, track_id: str, clip_id: str, reversed: bool = True) -> dict[str, Any]:
        clip = self._find_clip(track_id, clip_id); clip["reversed"] = bool(reversed)
        return {"track_id": track_id, "clip_id": clip_id, "reversed": bool(reversed)}

    def _tool_create_sampler(self, track_id: str, sampler_id: str, name: str = "Sampler") -> dict[str, Any]:
        track = self._find_track(track_id)
        if any(x.get("id") == sampler_id for x in track.get("instruments", [])): raise ToolError("sampler id already exists")
        sampler = {"id": sampler_id, "type": "sampler", "name": name, "mappings": []}
        track.setdefault("instruments", []).append(sampler)
        return deepcopy(sampler)

    def _tool_map_sample_slice(self, track_id: str, sampler_id: str, asset_id: str, note: int, source_start: float, source_end: float) -> dict[str, Any]:
        self._find_asset(asset_id)
        track = self._find_track(track_id)
        sampler = next((x for x in track.get("instruments", []) if x.get("id") == sampler_id and x.get("type") == "sampler"), None)
        if sampler is None: raise ToolError("sampler was not found")
        mapping = {"note": int(note), "asset_id": asset_id, "source_start": float(source_start), "source_end": float(source_end)}
        sampler["mappings"].append(mapping)
        return deepcopy(mapping)

    def _tool_register_derived_asset(self, asset_id: str, name: str, duration_seconds: float, derived_from: list[str], operations: list[dict[str, Any]]) -> dict[str, Any]:
        if any(x.get("id") == asset_id for x in self._project.assets): raise ToolError("asset id already exists")
        for source in derived_from: self._find_asset(source)
        asset = {"id": asset_id, "kind": "audio", "name": name, "duration_seconds": float(duration_seconds),
                 "provenance": {"source": "derived", "derived_from": list(derived_from), "operations": deepcopy(operations)}}
        self._project.assets.append(asset)
        return deepcopy(asset)
