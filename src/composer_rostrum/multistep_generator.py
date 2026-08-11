from __future__ import annotations

import argparse
import json
import random
from copy import deepcopy
from pathlib import Path

from .models import MusicProject, RostrumTask
from .music_theory import triad_pitch_classes

CHORDS = ["C_major", "D_minor", "E_minor", "F_major", "G_major", "A_minor"]


def _nearest_pitch_with_pc(reference: int, pitch_class: int) -> int:
    candidates = [p for p in range(max(0, reference - 12), min(127, reference + 12) + 1) if p % 12 == pitch_class]
    return min(candidates, key=lambda p: (abs(p - reference), p))


def _base(seed: int, family: str, tracks: list[dict], key: str = "C_major") -> MusicProject:
    return MusicProject(tempo=120.0, meter="4/4", key=key, tracks=deepcopy(tracks), assets=[],
                        metadata={"generator": "rostrum-multistep-v1", "seed": seed, "family": family})


def generate_multistep_task(index: int, seed: int) -> RostrumTask:
    rng = random.Random(seed)
    family = ["repair-quantize", "duplicate-transform", "repair-transpose"][index % 3]
    task_id = f"L1M-{index + 1:03d}-{family}"

    if family == "repair-quantize":
        chord = rng.choice(CHORDS)
        chord_pcs = triad_pitch_classes(chord)
        good_pc = rng.choice(sorted(chord_pcs))
        good_pitch = _nearest_pitch_with_pc(48, good_pc)
        bad_pitch = next(p for p in range(good_pitch - 2, good_pitch + 3) if p % 12 not in chord_pcs)
        start = rng.choice([1.11, 1.13, 1.37, 1.61])
        tracks = [
            {"id": "bass", "name": "Bass", "kind": "midi", "clips": [{"id": "bassline", "kind": "midi", "start": 0.0, "length": 4.0,
                "notes": [{"id": "bass-n0", "pitch": bad_pitch, "start": start, "duration": 0.5, "velocity": 92}]}]},
            {"id": "melody", "name": "Melody", "kind": "midi", "clips": [{"id": "lead", "kind": "midi", "start": 0.0, "length": 4.0,
                "notes": [{"id": "lead-n0", "pitch": 72, "start": 0.0, "duration": 1.0, "velocity": 86}]}]},
        ]
        project = _base(seed, family, tracks, key=chord)
        return RostrumTask(task_id, "L1",
            f"The only note in clip 'bassline' on track 'bass' conflicts with the {chord} chord. Move it to the nearest {chord} chord tone, then quantize only that note to the nearest 0.25 beats. Leave the melody and every other property untouched.",
            project, ["inspect_project", "set_note_pitch", "set_note_start"],
            [{"type": "note_in_chord", "track_id": "bass", "clip_id": "bassline", "note_id": "bass-n0", "chord": chord},
             {"type": "note_quantized", "track_id": "bass", "clip_id": "bassline", "note_id": "bass-n0", "grid": 0.25},
             {"type": "preserve_paths", "paths": ["tracks.1", "tempo", "meter", "key", "assets", "metadata"]}],
            ["multistep", "bass", "harmony", "quantization", "preservation"])

    if family == "duplicate-transform":
        notes = [{"id": f"n{i}", "pitch": p, "start": i * 0.5, "duration": 0.45, "velocity": 80 + i}
                 for i, p in enumerate(rng.sample(range(58, 72), 5))]
        tracks = [{"id": "keys", "name": "Keys", "kind": "midi", "clips": [
            {"id": "call", "kind": "midi", "start": 0.0, "length": 4.0, "notes": deepcopy(notes)}]}]
        project = _base(seed, family, tracks)
        interval = rng.choice([3, 5, 7])
        return RostrumTask(task_id, "L1",
            f"Create a response from clip 'call' on track 'keys': duplicate it as clip 'response' starting at beat 4, then transpose only 'response' up {interval} semitones. Preserve 'call' exactly.",
            project, ["inspect_project", "duplicate_clip", "transpose_notes"],
            [{"type": "clip_transposition_relation", "track_id": "keys", "source_clip_id": "call", "target_clip_id": "response", "semitones": interval, "target_start": 4.0},
             {"type": "preserve_paths", "paths": ["tracks.0.clips.0", "tempo", "meter", "key", "assets", "metadata"]}],
            ["multistep", "arrangement", "call-response", "transposition", "preservation"])

    chord = rng.choice(CHORDS)
    pcs = sorted(triad_pitch_classes(chord))
    pitches = [_nearest_pitch_with_pc(60, pc) for pc in pcs]
    notes = [{"id": f"n{i}", "pitch": pitch, "start": 0.0, "duration": 2.0, "velocity": 88} for i, pitch in enumerate(pitches)]
    bad_i = rng.randrange(3)
    notes[bad_i]["pitch"] = next(p for p in range(notes[bad_i]["pitch"] - 2, notes[bad_i]["pitch"] + 3) if p % 12 not in set(pcs))
    tracks = [{"id": "keys", "name": "Keys", "kind": "midi", "clips": [{"id": "chord", "kind": "midi", "start": 0.0, "length": 2.0, "notes": notes}]}]
    project = _base(seed, family, tracks, key=chord)
    octave = 12
    return RostrumTask(task_id, "L1",
        f"Repair clip 'chord' on track 'keys' so it forms a {chord} triad by changing the one wrong note, then transpose the repaired chord up {octave} semitones. Preserve timing, velocities, durations, and project settings.",
        project, ["inspect_project", "set_note_pitch", "transpose_notes"],
        [{"type": "triad_pitch_classes", "track_id": "keys", "clip_id": "chord", "chord": chord},
         {"type": "all_notes_transposed_from_repaired_triad", "track_id": "keys", "clip_id": "chord", "chord": chord, "semitones": octave},
         {"type": "preserve_paths", "paths": ["tempo", "meter", "key", "assets", "metadata"]}],
        ["multistep", "harmony", "repair", "transposition"])


def generate_multistep_suite(count: int = 48, seed: int = 20260811) -> list[RostrumTask]:
    master = random.Random(seed)
    return [generate_multistep_task(i, master.randrange(0, 2**31)) for i in range(count)]


def write_multistep_suite(output: str | Path, count: int = 48, seed: int = 20260811) -> list[Path]:
    directory = Path(output); directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for task in generate_multistep_suite(count, seed):
        path = directory / f"{task.id}.json"
        path.write_text(json.dumps(task.to_dict(), indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate multi-step Composer Rostrum tasks")
    parser.add_argument("output"); parser.add_argument("--count", type=int, default=48); parser.add_argument("--seed", type=int, default=20260811)
    args = parser.parse_args(); paths = write_multistep_suite(args.output, args.count, args.seed)
    print(f"wrote {len(paths)} multi-step tasks to {Path(args.output)}")


if __name__ == "__main__": main()
