from __future__ import annotations

import re
from typing import Any, Protocol

from .environment import MusicEnvironment
from .models import RostrumTask
from .music_theory import nearest_pitch_in_scale, triad_pitch_classes


class Agent(Protocol):
    def solve(self, task: RostrumTask, environment: MusicEnvironment) -> None:
        """Use only the environment tool surface to solve the task."""
        ...


def _clip(project: dict[str, Any], track_id: str, clip_id: str) -> dict[str, Any]:
    track = next(track for track in project["tracks"] if track.get("id") == track_id)
    return next(clip for clip in track.get("clips", []) if clip.get("id") == clip_id)


def _nearest_pitch_with_pc(reference: int, pitch_class: int) -> int:
    candidates = [pitch for pitch in range(max(0, reference - 12), min(127, reference + 12) + 1) if pitch % 12 == pitch_class]
    return min(candidates, key=lambda pitch: (abs(pitch - reference), pitch))


class ReferenceAgent:
    """Deterministic baseline for benchmark validation, using only prompt + tools."""

    def solve(self, task: RostrumTask, environment: MusicEnvironment) -> None:
        project = environment.call("inspect_project")
        prompt = task.prompt

        if "set_tempo" in environment.allowed_tools:
            match = re.search(r"tempo to ([0-9]+(?:\.[0-9]+)?) BPM", prompt, re.I)
            if match:
                environment.call("set_tempo", bpm=float(match.group(1))); return

        if "set_key" in environment.allowed_tools:
            match = re.search(r"key to ([A-G](?:#|b)?_(?:major|minor))", prompt, re.I)
            if match:
                environment.call("set_key", key=match.group(1)); return

        if "set_meter" in environment.allowed_tools:
            match = re.search(r"meter to ([0-9]+/[0-9]+)", prompt, re.I)
            if match:
                environment.call("set_meter", meter=match.group(1)); return

        if "mute_track" in environment.allowed_tools:
            match = re.search(r"Mute track '([^']+)'", prompt, re.I)
            if match:
                environment.call("mute_track", track_id=match.group(1), muted=True); return

        if "set_track_gain" in environment.allowed_tools:
            match = re.search(r"Set track '([^']+)' gain to (-?[0-9]+(?:\.[0-9]+)?) dB", prompt, re.I)
            if match:
                environment.call("set_track_gain", track_id=match.group(1), gain_db=float(match.group(2))); return

        if "transpose_notes" in environment.allowed_tools:
            match = re.search(r"Transpose clip '([^']+)' on track '([^']+)' (up|down) (\d+) semitones", prompt, re.I)
            if match:
                clip_id, track_id, direction, amount = match.groups()
                semitones = int(amount) * (1 if direction.lower() == "up" else -1)
                environment.call("transpose_notes", track_id=track_id, clip_id=clip_id, semitones=semitones); return

        if "quantize_notes" in environment.allowed_tools:
            match = re.search(r"Quantize clip '([^']+)' on track '([^']+)' to the nearest ([0-9.]+) beats", prompt, re.I)
            if match:
                clip_id, track_id, grid = match.groups()
                environment.call("quantize_notes", track_id=track_id, clip_id=clip_id, grid=float(grid)); return

        if "set_note_pitch" in environment.allowed_tools and "triad" in prompt.lower():
            match = re.search(r"clip '([^']+)' on track '([^']+)'.*?([A-G](?:#|b)?_(?:major|minor)) triad", prompt, re.I)
            if match:
                clip_id, track_id, chord = match.groups()
                notes = _clip(project, track_id, clip_id)["notes"]
                target = triad_pitch_classes(chord)
                current = {int(note["pitch"]) % 12 for note in notes}
                missing = list(target - current)
                wrong = [note for note in notes if int(note["pitch"]) % 12 not in target]
                if len(missing) == 1 and len(wrong) == 1:
                    note = wrong[0]
                    pitch = _nearest_pitch_with_pc(int(note["pitch"]), missing[0])
                    environment.call("set_note_pitch", track_id=track_id, clip_id=clip_id, note_id=note["id"], pitch=pitch)
                    return

        if "set_note_pitch" in environment.allowed_tools and "conform to" in prompt.lower():
            match = re.search(r"clip '([^']+)' on track '([^']+)' conform to ([A-G](?:#|b)?_(?:major|minor))", prompt, re.I)
            if match:
                clip_id, track_id, key = match.groups()
                notes = _clip(project, track_id, clip_id)["notes"]
                for note in notes:
                    corrected = nearest_pitch_in_scale(int(note["pitch"]), key)
                    if corrected != int(note["pitch"]):
                        environment.call("set_note_pitch", track_id=track_id, clip_id=clip_id, note_id=note["id"], pitch=corrected)
                return
