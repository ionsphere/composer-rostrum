from __future__ import annotations

import hashlib
import json
import math
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
    def canonical(value):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in value.items()}
        if isinstance(value, list):
            return [canonical(v) for v in value]
        return value
    payload = json.dumps(canonical(project.to_dict()), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _diff_paths(before: Any, after: Any, prefix: str = "") -> list[str]:
    if type(before) in (int, float) and type(after) in (int, float):
        return [] if before == after else [prefix or "$root"]
    if type(before) is not type(after): return [prefix or "$root"]
    if isinstance(before, dict):
        paths: list[str] = []
        for key in sorted(set(before) | set(after)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in before or key not in after: paths.append(path)
            else: paths.extend(_diff_paths(before[key], after[key], path))
        return paths
    if isinstance(before, list):
        paths: list[str] = []
        for index in range(max(len(before), len(after))):
            path = f"{prefix}.{index}" if prefix else str(index)
            if index >= len(before) or index >= len(after): paths.append(path)
            else: paths.extend(_diff_paths(before[index], after[index], path))
        return paths
    return [] if before == after else [prefix or "$root"]


class MusicEnvironment:
    def __init__(self, project: MusicProject, allowed_tools: list[str]):
        self._project = deepcopy(project)
        self.allowed_tools = frozenset(allowed_tools)
        self.trajectory: list[TrajectoryEvent] = []

    @property
    def project(self) -> MusicProject: return deepcopy(self._project)

    def call(self, tool: str, **arguments: Any) -> Any:
        before = deepcopy(self._project); before_hash = project_hash(before)
        try:
            if tool not in self.allowed_tools: raise ToolError(f"tool {tool!r} is not allowed for this task")
            handler = getattr(self, f"_tool_{tool}", None)
            if handler is None: raise ToolError(f"tool {tool!r} is not implemented")
            result = handler(**arguments)
        except Exception as exc:
            self.trajectory.append(TrajectoryEvent(len(self.trajectory), tool, deepcopy(arguments), None, before_hash,
                project_hash(self._project), _diff_paths(before.to_dict(), self._project.to_dict()), f"{type(exc).__name__}: {exc}"))
            raise
        self.trajectory.append(TrajectoryEvent(len(self.trajectory), tool, deepcopy(arguments), deepcopy(result), before_hash,
            project_hash(self._project), _diff_paths(before.to_dict(), self._project.to_dict())))
        return deepcopy(result)

    def _tool_inspect_project(self, path: str | None = None) -> Any:
        value: Any = self._project.to_dict()
        if path is None: return value
        for part in path.split("."): value = value[int(part)] if isinstance(value, list) else value[part]
        return value

    def _find_track(self, track_id: str) -> dict[str, Any]:
        for track in self._project.tracks:
            if track.get("id") == track_id: return track
        raise ToolError(f"track {track_id!r} was not found")

    def _find_asset(self, asset_id: str) -> dict[str, Any]:
        for asset in self._project.assets:
            if asset.get("id") == asset_id: return asset
        raise ToolError(f"asset {asset_id!r} was not found")

    def _find_clip(self, track_id: str, clip_id: str) -> dict[str, Any]:
        track = self._find_track(track_id)
        for clip in track.get("clips", []):
            if clip.get("id") == clip_id: return clip
        raise ToolError(f"clip {clip_id!r} was not found on track {track_id!r}")

    def _find_note(self, track_id: str, clip_id: str, note_id: str) -> dict[str, Any]:
        clip = self._find_clip(track_id, clip_id)
        for note in clip.get("notes", []):
            if note.get("id") == note_id: return note
        raise ToolError(f"note {note_id!r} was not found in clip {clip_id!r}")

    def _tool_set_tempo(self, bpm: float) -> dict[str, float]:
        bpm = float(bpm)
        if bpm <= 0: raise ToolError("tempo must be greater than zero")
        self._project.tempo = bpm; return {"tempo": bpm}

    def _tool_add_track(self, track_id: str, name: str, kind: str, gain_db: float = 0) -> dict:
        if kind not in ("midi", "audio") or not math.isfinite(gain_db) or not -120 <= gain_db <= 24:
            raise ToolError("invalid track kind or gain")
        if any(t["id"] == track_id for t in self._project.tracks):
            raise ToolError("duplicate track ID")
        track = {"id": track_id, "name": name, "kind": kind, "gain_db": float(gain_db), "clips": []}
        self._project.tracks.append(track)
        return deepcopy(track)

    def _append_clip(self, track_id: str, clip: dict) -> dict:
        track = self._find_track(track_id)
        if track["kind"] != clip["kind"]:
            raise ToolError("clip kind must match track kind")
        if any(c["id"] == clip["id"] for c in track.get("clips", [])):
            raise ToolError("duplicate clip ID")
        track.setdefault("clips", []).append(deepcopy(clip))
        return deepcopy(clip)

    def _tool_add_midi_clip(self, track_id: str, clip_id: str, start: float,
                            length: float, notes: list[dict[str, Any]]) -> dict:
        if not math.isfinite(start) or not math.isfinite(length) or start < 0 or length <= 0:
            raise ToolError("invalid MIDI clip extent")
        seen = set()
        for note in notes:
            if note["id"] in seen or not 0 <= note["pitch"] <= 127 or not 1 <= note["velocity"] <= 127:
                raise ToolError("invalid note identity, pitch or velocity")
            seen.add(note["id"])
            if not all(math.isfinite(note[k]) for k in ("start", "duration")) or note["start"] < 0 or note["duration"] <= 0 or note["start"] + note["duration"] > length:
                raise ToolError("note must fit inside clip")
        return self._append_clip(track_id, {"id": clip_id, "kind": "midi", "start": start,
                                          "length": length, "notes": notes})

    def _tool_add_audio_clip(self, track_id: str, clip_id: str, asset_id: str,
                             timeline_start_beats: float, source_start: float, source_end: float) -> dict:
        asset = self._find_asset(asset_id)
        if not math.isfinite(timeline_start_beats) or timeline_start_beats < 0 or not 0 <= source_start < source_end <= asset["duration_seconds"]:
            raise ToolError("invalid audio extent")
        return self._append_clip(track_id, {"id": clip_id, "kind": "audio", "asset_id": asset_id,
            "timeline_start_beats": timeline_start_beats, "source_start": source_start,
            "source_end": source_end, "pitch_semitones": 0.0, "stretch_ratio": 1.0, "reversed": False})

    def _tool_set_clip_fades(self, track_id: str, clip_id: str,
                             fade_in_seconds: float, fade_out_seconds: float) -> dict:
        clip = self._find_clip(track_id, clip_id)
        if "asset_id" not in clip:
            raise ToolError("fades currently require an audio clip")
        duration = (clip["source_end"] - clip["source_start"]) * clip.get("stretch_ratio", 1)
        if any(not math.isfinite(v) or not 0 <= v <= duration for v in (fade_in_seconds, fade_out_seconds)):
            raise ToolError("fade lengths must fit inside the audio item")
        clip.update(fade_in_seconds=float(fade_in_seconds), fade_out_seconds=float(fade_out_seconds))
        return deepcopy(clip)

    def _tool_set_key(self, key: str | None) -> dict[str, str | None]: self._project.key = key; return {"key": key}
    def _tool_set_meter(self, meter: str) -> dict[str, str]:
        if "/" not in meter: raise ToolError("meter must look like '4/4'")
        self._project.meter = meter; return {"meter": meter}
    def _tool_mute_track(self, track_id: str, muted: bool = True) -> dict[str, Any]:
        self._find_track(track_id)["muted"] = bool(muted); return {"track_id": track_id, "muted": bool(muted)}
    def _tool_rename_track(self, track_id: str, name: str) -> dict[str, str]:
        self._find_track(track_id)["name"] = str(name); return {"track_id": track_id, "name": str(name)}
    def _tool_set_track_gain(self, track_id: str, gain_db: float) -> dict[str, Any]:
        self._find_track(track_id)["gain_db"] = float(gain_db); return {"track_id": track_id, "gain_db": float(gain_db)}

    def _tool_set_track_pan(self, track_id: str, pan: float) -> dict[str, Any]:
        if not -1 <= float(pan) <= 1:
            raise ToolError("pan must be between -1 and 1")
        self._find_track(track_id)["pan"] = float(pan)
        return {"track_id": track_id, "pan": float(pan)}

    def _tool_add_send(self, track_id: str, destination_id: str, gain_db: float = 0) -> dict[str, Any]:
        track = self._find_track(track_id)
        self._find_track(destination_id)
        if track_id == destination_id or any(s["destination_id"] == destination_id for s in track.get("sends", [])):
            raise ToolError("self/duplicate sends are not allowed")
        send = {"destination_id": destination_id, "gain_db": float(gain_db)}
        track.setdefault("sends", []).append(send)
        return send

    def _tool_add_gain_effect(self, track_id: str, effect_id: str, gain_db: float) -> dict[str, Any]:
        track = self._find_track(track_id)
        if any(e["id"] == effect_id for e in track.get("effects", [])):
            raise ToolError("duplicate effect ID")
        effect = {"id": effect_id, "type": "gain", "gain_db": float(gain_db)}
        track.setdefault("effects", []).append(effect)
        return effect

    def _tool_transpose_notes(self, track_id: str, clip_id: str, semitones: int) -> dict[str, Any]:
        clip = self._find_clip(track_id, clip_id); notes = clip.get("notes", []); delta = int(semitones)
        for note in notes:
            if not 0 <= int(note["pitch"]) + delta <= 127: raise ToolError("transpose would exceed MIDI pitch range")
        for note in notes: note["pitch"] = int(note["pitch"]) + delta
        return {"track_id": track_id, "clip_id": clip_id, "semitones": delta, "notes_changed": len(notes)}

    def _tool_quantize_notes(self, track_id: str, clip_id: str, grid: float) -> dict[str, Any]:
        grid = float(grid)
        if grid <= 0: raise ToolError("quantize grid must be greater than zero")
        clip = self._find_clip(track_id, clip_id)
        for note in clip.get("notes", []): note["start"] = round(float(note["start"]) / grid) * grid
        return {"track_id": track_id, "clip_id": clip_id, "grid": grid}

    def _tool_set_note_pitch(self, track_id: str, clip_id: str, note_id: str, pitch: int) -> dict[str, Any]:
        pitch = int(pitch)
        if not 0 <= pitch <= 127: raise ToolError("MIDI pitch must be between 0 and 127")
        self._find_note(track_id, clip_id, note_id)["pitch"] = pitch
        return {"track_id": track_id, "clip_id": clip_id, "note_id": note_id, "pitch": pitch}

    def _tool_set_note_start(self, track_id: str, clip_id: str, note_id: str, start: float) -> dict[str, Any]:
        start = float(start)
        if start < 0: raise ToolError("note start must be non-negative")
        self._find_note(track_id, clip_id, note_id)["start"] = start
        return {"track_id": track_id, "clip_id": clip_id, "note_id": note_id, "start": start}

    def _tool_duplicate_clip(self, track_id: str, source_clip_id: str, new_clip_id: str, start: float) -> dict[str, Any]:
        track = self._find_track(track_id)
        if any(c.get("id") == new_clip_id for c in track.get("clips", [])): raise ToolError("clip id already exists")
        source = self._find_clip(track_id, source_clip_id); duplicate = deepcopy(source)
        duplicate["id"] = new_clip_id; duplicate["start"] = float(start)
        for note in duplicate.get("notes", []): note["id"] = f"{new_clip_id}-{note['id']}"
        track.setdefault("clips", []).append(duplicate)
        return deepcopy(duplicate)

    def _tool_trim_clip(self, track_id: str, clip_id: str, source_start: float, source_end: float) -> dict[str, Any]:
        clip = self._find_clip(track_id, clip_id)
        if source_start < 0 or source_end <= source_start: raise ToolError("invalid source range")
        asset = self._find_asset(clip["asset_id"])
        if source_end > float(asset["duration_seconds"]): raise ToolError("trim exceeds source asset")
        clip["source_start"] = float(source_start); clip["source_end"] = float(source_end)
        return {"track_id": track_id, "clip_id": clip_id, "source_start": float(source_start), "source_end": float(source_end)}

    def _tool_split_audio_clip(self, track_id: str, clip_id: str, new_clip_id: str,
                               source_seconds: float) -> dict[str, Any]:
        track = self._find_track(track_id)
        clip = self._find_clip(track_id, clip_id)
        if clip.get("kind") != "audio" and "asset_id" not in clip:
            raise ToolError("split requires an audio clip")
        if any(c["id"] == new_clip_id for c in track.get("clips", [])):
            raise ToolError("clip id already exists")
        cut = float(source_seconds)
        if not math.isfinite(cut) or not clip["source_start"] < cut < clip["source_end"]:
            raise ToolError("split point must lie inside the source range")
        ratio = float(clip.get("stretch_ratio", 1))
        left_duration = (cut - clip["source_start"]) * ratio
        right_duration = (clip["source_end"] - cut) * ratio
        fade_in = float(clip.get("fade_in_seconds", 0))
        fade_out = float(clip.get("fade_out_seconds", 0))
        if fade_in > left_duration or fade_out > right_duration:
            raise ToolError("split would cut through an outer fade")
        right = deepcopy(clip)
        right["id"] = new_clip_id
        right["source_start"] = cut
        right["timeline_start_beats"] = round(clip["timeline_start_beats"] + left_duration * self._project.tempo / 60, 9)
        clip["source_end"] = cut
        if "fade_out_seconds" in clip:
            clip["fade_out_seconds"] = 0.0
        if "fade_in_seconds" in right:
            right["fade_in_seconds"] = 0.0
        track.setdefault("clips", []).append(right)
        return {"track_id": track_id, "left_clip_id": clip_id, "right_clip_id": new_clip_id,
                "source_seconds": cut}

    def _tool_move_audio_clip(self, track_id: str, clip_id: str, timeline_start_beats: float) -> dict[str, Any]:
        clip = self._find_clip(track_id, clip_id)
        start = float(timeline_start_beats)
        if "asset_id" not in clip or not math.isfinite(start) or start < 0:
            raise ToolError("move requires an audio clip and non-negative beat position")
        clip["timeline_start_beats"] = start
        return {"track_id": track_id, "clip_id": clip_id, "timeline_start_beats": start}

    def _tool_set_clip_pitch(self, track_id: str, clip_id: str, semitones: float) -> dict[str, Any]:
        self._find_clip(track_id, clip_id)["pitch_semitones"] = float(semitones)
        return {"track_id": track_id, "clip_id": clip_id, "pitch_semitones": float(semitones)}
    def _tool_stretch_clip(self, track_id: str, clip_id: str, ratio: float) -> dict[str, Any]:
        ratio = float(ratio)
        if ratio <= 0: raise ToolError("stretch ratio must be greater than zero")
        self._find_clip(track_id, clip_id)["stretch_ratio"] = ratio; return {"track_id": track_id, "clip_id": clip_id, "stretch_ratio": ratio}
    def _tool_reverse_clip(self, track_id: str, clip_id: str, reversed: bool = True) -> dict[str, Any]:
        self._find_clip(track_id, clip_id)["reversed"] = bool(reversed); return {"track_id": track_id, "clip_id": clip_id, "reversed": bool(reversed)}
    def _tool_create_sampler(self, track_id: str, sampler_id: str, name: str = "Sampler") -> dict[str, Any]:
        track = self._find_track(track_id)
        if any(x.get("id") == sampler_id for x in track.get("instruments", [])): raise ToolError("sampler id already exists")
        sampler = {"id": sampler_id, "type": "sampler", "name": name, "mappings": []}; track.setdefault("instruments", []).append(sampler); return deepcopy(sampler)
    def _tool_map_sample_slice(self, track_id: str, sampler_id: str, asset_id: str, note: int, source_start: float, source_end: float) -> dict[str, Any]:
        self._find_asset(asset_id); track = self._find_track(track_id)
        sampler = next((x for x in track.get("instruments", []) if x.get("id") == sampler_id and x.get("type") == "sampler"), None)
        if sampler is None: raise ToolError("sampler was not found")
        mapping = {"note": int(note), "asset_id": asset_id, "source_start": float(source_start), "source_end": float(source_end)}; sampler["mappings"].append(mapping); return deepcopy(mapping)
    def _tool_register_derived_asset(self, asset_id: str, name: str, duration_seconds: float, derived_from: list[str], operations: list[dict[str, Any]]) -> dict[str, Any]:
        if any(x.get("id") == asset_id for x in self._project.assets): raise ToolError("asset id already exists")
        for source in derived_from: self._find_asset(source)
        asset = {"id": asset_id, "kind": "audio", "name": name, "duration_seconds": float(duration_seconds),
                 "provenance": {"source": "derived", "derived_from": list(derived_from), "operations": deepcopy(operations)}}
        self._project.assets.append(asset); return deepcopy(asset)
