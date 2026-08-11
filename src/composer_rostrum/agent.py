from __future__ import annotations

import re
from typing import Any, Protocol

from .environment import MusicEnvironment
from .models import RostrumTask
from .music_theory import nearest_pitch_in_scale, triad_pitch_classes


class Agent(Protocol):
    def solve(self, task: RostrumTask, environment: MusicEnvironment) -> None: ...


def _clip(project: dict[str, Any], track_id: str, clip_id: str) -> dict[str, Any]:
    track = next(t for t in project["tracks"] if t.get("id") == track_id)
    return next(c for c in track.get("clips", []) if c.get("id") == clip_id)


def _nearest_pitch_with_pc(reference: int, pitch_class: int) -> int:
    candidates = [p for p in range(max(0, reference - 12), min(127, reference + 12) + 1) if p % 12 == pitch_class]
    return min(candidates, key=lambda p: (abs(p - reference), p))


def _repair_triad(environment: MusicEnvironment, project: dict[str, Any], track_id: str, clip_id: str, chord: str) -> None:
    notes = _clip(project, track_id, clip_id)["notes"]; target = triad_pitch_classes(chord)
    current = {int(n["pitch"]) % 12 for n in notes}; missing = list(target - current)
    wrong = [n for n in notes if int(n["pitch"]) % 12 not in target]
    if len(missing) == 1 and len(wrong) == 1:
        note = wrong[0]; pitch = _nearest_pitch_with_pc(int(note["pitch"]), missing[0])
        environment.call("set_note_pitch", track_id=track_id, clip_id=clip_id, note_id=note["id"], pitch=pitch)


class ReferenceAgent:
    """Deterministic benchmark validator. It uses only prompt text and environment observations."""

    def solve(self, task: RostrumTask, environment: MusicEnvironment) -> None:
        project = environment.call("inspect_project"); prompt = task.prompt

        m = re.search(r"only note in clip '([^']+)' on track '([^']+)' conflicts with the ([A-G](?:#|b)?_(?:major|minor)) chord.*nearest ([A-G](?:#|b)?_(?:major|minor)) chord tone, then quantize only that note to the nearest ([0-9.]+) beats", prompt, re.I)
        if m and {"set_note_pitch", "set_note_start"}.issubset(environment.allowed_tools):
            clip_id, track_id, chord, _, grid_s = m.groups(); note = _clip(project, track_id, clip_id)["notes"][0]
            pcs = triad_pitch_classes(chord); pitch = min((_nearest_pitch_with_pc(int(note["pitch"]), pc) for pc in pcs), key=lambda p: (abs(p-int(note["pitch"])), p))
            environment.call("set_note_pitch", track_id=track_id, clip_id=clip_id, note_id=note["id"], pitch=pitch)
            grid = float(grid_s); environment.call("set_note_start", track_id=track_id, clip_id=clip_id, note_id=note["id"], start=round(float(note["start"])/grid)*grid); return

        m = re.search(r"duplicate it as clip '([^']+)' starting at beat ([0-9.]+), then transpose only '([^']+)' up (\d+) semitones", prompt, re.I)
        if m and {"duplicate_clip", "transpose_notes"}.issubset(environment.allowed_tools):
            new_id, start, again_id, amount = m.groups(); source = re.search(r"from clip '([^']+)' on track '([^']+)'", prompt, re.I)
            if source:
                source_id, track_id = source.groups(); environment.call("duplicate_clip", track_id=track_id, source_clip_id=source_id, new_clip_id=new_id, start=float(start)); environment.call("transpose_notes", track_id=track_id, clip_id=again_id, semitones=int(amount)); return

        m = re.search(r"Repair clip '([^']+)' on track '([^']+)' so it forms a ([A-G](?:#|b)?_(?:major|minor)) triad.*then transpose the repaired chord up (\d+) semitones", prompt, re.I)
        if m and {"set_note_pitch", "transpose_notes"}.issubset(environment.allowed_tools):
            clip_id, track_id, chord, amount = m.groups(); _repair_triad(environment, project, track_id, clip_id, chord); environment.call("transpose_notes", track_id=track_id, clip_id=clip_id, semitones=int(amount)); return

        if "set_tempo" in environment.allowed_tools:
            m = re.search(r"tempo to ([0-9]+(?:\.[0-9]+)?) BPM", prompt, re.I)
            if m: environment.call("set_tempo", bpm=float(m.group(1))); return
        if "set_key" in environment.allowed_tools:
            m = re.search(r"key to ([A-G](?:#|b)?_(?:major|minor))", prompt, re.I)
            if m: environment.call("set_key", key=m.group(1)); return
        if "set_meter" in environment.allowed_tools:
            m = re.search(r"meter to ([0-9]+/[0-9]+)", prompt, re.I)
            if m: environment.call("set_meter", meter=m.group(1)); return
        if "mute_track" in environment.allowed_tools:
            m = re.search(r"Mute track '([^']+)'", prompt, re.I)
            if m: environment.call("mute_track", track_id=m.group(1), muted=True); return
        if "set_track_gain" in environment.allowed_tools:
            m = re.search(r"Set track '([^']+)' gain to (-?[0-9]+(?:\.[0-9]+)?) dB", prompt, re.I)
            if m: environment.call("set_track_gain", track_id=m.group(1), gain_db=float(m.group(2))); return
        if "transpose_notes" in environment.allowed_tools:
            m = re.search(r"Transpose clip '([^']+)' on track '([^']+)' (up|down) (\d+) semitones", prompt, re.I)
            if m:
                clip_id, track_id, direction, amount = m.groups(); environment.call("transpose_notes", track_id=track_id, clip_id=clip_id, semitones=int(amount)*(1 if direction.lower()=="up" else -1)); return
        if "quantize_notes" in environment.allowed_tools:
            m = re.search(r"Quantize clip '([^']+)' on track '([^']+)' to the nearest ([0-9.]+) beats", prompt, re.I)
            if m: environment.call("quantize_notes", track_id=m.group(2), clip_id=m.group(1), grid=float(m.group(3))); return
        if "set_note_pitch" in environment.allowed_tools and "triad" in prompt.lower():
            m = re.search(r"clip '([^']+)' on track '([^']+)'.*?([A-G](?:#|b)?_(?:major|minor)) triad", prompt, re.I)
            if m: _repair_triad(environment, project, m.group(2), m.group(1), m.group(3)); return
        if "set_note_pitch" in environment.allowed_tools and "conform to" in prompt.lower():
            m = re.search(r"clip '([^']+)' on track '([^']+)' conform to ([A-G](?:#|b)?_(?:major|minor))", prompt, re.I)
            if m:
                clip_id, track_id, key = m.groups()
                for note in _clip(project, track_id, clip_id)["notes"]:
                    corrected = nearest_pitch_in_scale(int(note["pitch"]), key)
                    if corrected != int(note["pitch"]): environment.call("set_note_pitch", track_id=track_id, clip_id=clip_id, note_id=note["id"], pitch=corrected)
                return
