from __future__ import annotations

import argparse
import json
import random
from copy import deepcopy
from pathlib import Path

from .models import MusicProject, RostrumTask
from .music_theory import scale_pitch_classes, triad_pitch_classes

CHORDS = ["C_major", "D_minor", "E_minor", "F_major", "G_major", "A_minor"]
KEYS = ["C_major", "A_minor", "G_major", "E_minor", "F_major", "D_minor"]


def _pitch_for_pc(pc: int, floor: int = 60) -> int:
    return next(pitch for pitch in range(floor, floor + 12) if pitch % 12 == pc)


def _project(notes: list[dict], seed: int, family: str, key: str = "C_major") -> MusicProject:
    return MusicProject(
        tempo=120.0, meter="4/4", key=key,
        tracks=[{"id": "keys", "name": "Keys", "kind": "midi", "muted": False, "gain_db": 0.0,
                 "clips": [{"id": "phrase", "kind": "midi", "start": 0.0, "length": 4.0, "notes": deepcopy(notes)}]}],
        assets=[], metadata={"generator": "rostrum-l1-v1", "seed": seed, "family": family})


def _preserve_project() -> dict:
    return {"type": "preserve_paths", "paths": ["tempo", "meter", "key", "assets", "metadata"]}


def generate_symbolic_task(index: int, seed: int) -> RostrumTask:
    rng = random.Random(seed)
    family = ["transpose", "quantize", "chord-repair", "scale-repair"][index % 4]
    task_id = f"L1-{index + 1:03d}-{family}"

    if family == "transpose":
        notes = [{"id": f"n{i}", "pitch": pitch, "start": float(i) * 0.5, "duration": 0.5, "velocity": 80 + i}
                 for i, pitch in enumerate(rng.sample(range(55, 73), 5))]
        project = _project(notes, seed, family)
        amount = rng.choice([2, 3, 5, 7]); direction = rng.choice(["up", "down"]); delta = amount if direction == "up" else -amount
        expected = deepcopy(notes)
        for note in expected: note["pitch"] += delta
        return RostrumTask(task_id, "L1",
            f"Transpose clip 'phrase' on track 'keys' {direction} {amount} semitones. Preserve its rhythm, velocities, durations, and every other project setting.",
            project, ["inspect_project", "transpose_notes"],
            [{"type": "project_property", "path": "tracks.0.clips.0.notes", "equals": expected}, _preserve_project()],
            ["symbolic", "transposition", "procedural"])

    if family == "quantize":
        grid = rng.choice([0.25, 0.5])
        starts = [0.08, 0.46, 1.03, 1.57, 2.04]
        notes = [{"id": f"n{i}", "pitch": 60 + i, "start": start, "duration": 0.4, "velocity": 90}
                 for i, start in enumerate(starts)]
        project = _project(notes, seed, family)
        expected = deepcopy(notes)
        for note in expected: note["start"] = round(note["start"] / grid) * grid
        return RostrumTask(task_id, "L1",
            f"Quantize clip 'phrase' on track 'keys' to the nearest {grid:g} beats. Do not alter pitch, duration, velocity, or anything outside the clip.",
            project, ["inspect_project", "quantize_notes"],
            [{"type": "notes_quantized", "track_id": "keys", "clip_id": "phrase", "grid": grid},
             {"type": "project_property", "path": "tracks.0.clips.0.notes", "equals": expected}, _preserve_project()],
            ["symbolic", "rhythm", "quantization", "procedural"])

    if family == "chord-repair":
        chord = rng.choice(CHORDS); pcs = sorted(triad_pitch_classes(chord)); pitches = [_pitch_for_pc(pc) for pc in pcs]
        notes = [{"id": f"n{i}", "pitch": pitch, "start": 0.0, "duration": 2.0, "velocity": 88} for i, pitch in enumerate(pitches)]
        bad_index = rng.randrange(3); bad_pitch = notes[bad_index]["pitch"] + 1
        if bad_pitch % 12 in set(pcs): bad_pitch += 1
        notes[bad_index]["pitch"] = bad_pitch
        project = _project(notes, seed, family, key=chord)
        return RostrumTask(task_id, "L1",
            f"Repair clip 'phrase' on track 'keys' so its three simultaneous notes form a {chord} triad. Exactly one note has the wrong pitch; change only that note's pitch and preserve everything else.",
            project, ["inspect_project", "set_note_pitch"],
            [{"type": "triad_pitch_classes", "track_id": "keys", "clip_id": "phrase", "chord": chord},
             {"type": "changed_note_count", "track_id": "keys", "clip_id": "phrase", "equals": 1}, _preserve_project()],
            ["symbolic", "harmony", "triad", "repair", "procedural"])

    key = rng.choice(KEYS); pcs = sorted(scale_pitch_classes(key))
    source_pitches = [_pitch_for_pc(pc) for pc in rng.sample(pcs, 6)]
    notes = [{"id": f"n{i}", "pitch": pitch, "start": i * 0.5, "duration": 0.45, "velocity": 84 + i} for i, pitch in enumerate(source_pitches)]
    bad_index = rng.randrange(len(notes)); original = notes[bad_index]["pitch"]
    candidates = [original + delta for delta in (-1, 1, -2, 2) if 0 <= original + delta <= 127 and (original + delta) % 12 not in set(pcs)]
    notes[bad_index]["pitch"] = candidates[0]
    project = _project(notes, seed, family, key=key)
    return RostrumTask(task_id, "L1",
        f"Make every note in clip 'phrase' on track 'keys' conform to {key}. Exactly one note is out of key; move only that note to the nearest in-key pitch and preserve rhythm, duration, velocity, and project state.",
        project, ["inspect_project", "set_note_pitch"],
        [{"type": "notes_in_scale", "track_id": "keys", "clip_id": "phrase", "key": key},
         {"type": "changed_note_count", "track_id": "keys", "clip_id": "phrase", "equals": 1}, _preserve_project()],
        ["symbolic", "scale", "repair", "procedural"])


def generate_symbolic_suite(count: int = 80, seed: int = 20260811) -> list[RostrumTask]:
    master = random.Random(seed)
    return [generate_symbolic_task(index, master.randrange(0, 2**31)) for index in range(count)]


def write_symbolic_suite(output: str | Path, count: int = 80, seed: int = 20260811) -> list[Path]:
    directory = Path(output); directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for task in generate_symbolic_suite(count, seed):
        path = directory / f"{task.id}.json"; path.write_text(json.dumps(task.to_dict(), indent=2) + "\n", encoding="utf-8"); paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic L1 symbolic Composer Rostrum tasks")
    parser.add_argument("output"); parser.add_argument("--count", type=int, default=80); parser.add_argument("--seed", type=int, default=20260811)
    args = parser.parse_args(); paths = write_symbolic_suite(args.output, args.count, args.seed)
    print(f"wrote {len(paths)} symbolic tasks to {Path(args.output)}")


if __name__ == "__main__": main()
