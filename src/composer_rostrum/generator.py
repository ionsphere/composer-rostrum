from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .models import MusicProject, RostrumTask


KEYS = ["C_major", "A_minor", "G_major", "E_minor", "F_major", "D_minor"]
METERS = ["4/4", "3/4", "6/8", "5/4"]
TRACK_IDS = ["drums", "bass", "keys"]


def _base_project(rng: random.Random, seed: int, family: str) -> MusicProject:
    return MusicProject(
        tempo=float(rng.choice([90, 100, 110, 120, 128, 140])),
        meter=rng.choice(METERS),
        key=rng.choice(KEYS),
        tracks=[
            {"id": "drums", "name": "Drums", "kind": "midi", "muted": False, "gain_db": 0.0},
            {"id": "bass", "name": "Bass", "kind": "midi", "muted": False, "gain_db": 0.0},
            {"id": "keys", "name": "Keys", "kind": "midi", "muted": False, "gain_db": 0.0},
        ],
        metadata={"generator": "rostrum-l0-v1", "seed": seed, "family": family},
    )


def _preserve_except(target: str) -> dict:
    all_paths = ["tempo", "meter", "key", "tracks", "metadata"]
    return {"type": "preserve_paths", "paths": [p for p in all_paths if p != target]}


def generate_task(index: int, seed: int) -> RostrumTask:
    rng = random.Random(seed)
    family = ["tempo", "key", "meter", "mute", "gain"][index % 5]
    project = _base_project(rng, seed, family)
    task_id = f"L0-{index + 1:03d}-{family}"

    if family == "tempo":
        choices = [x for x in [72, 96, 112, 124, 132, 150] if x != project.tempo]
        target = float(rng.choice(choices))
        return RostrumTask(task_id, "L0", f"Set the project tempo to {target:g} BPM. Change nothing else.", project,
            ["inspect_project", "set_tempo"],
            [{"type": "project_property", "path": "tempo", "equals": target}, _preserve_except("tempo")],
            ["mechanics", "tempo", "procedural"])

    if family == "key":
        target = rng.choice([x for x in KEYS if x != project.key])
        return RostrumTask(task_id, "L0", f"Set the project key to {target}. Change nothing else.", project,
            ["inspect_project", "set_key"],
            [{"type": "project_property", "path": "key", "equals": target}, _preserve_except("key")],
            ["mechanics", "key", "procedural"])

    if family == "meter":
        target = rng.choice([x for x in METERS if x != project.meter])
        return RostrumTask(task_id, "L0", f"Set the project meter to {target}. Change nothing else.", project,
            ["inspect_project", "set_meter"],
            [{"type": "project_property", "path": "meter", "equals": target}, _preserve_except("meter")],
            ["mechanics", "meter", "procedural"])

    track_id = rng.choice(TRACK_IDS)
    track_index = TRACK_IDS.index(track_id)
    if family == "mute":
        preserve = ["tempo", "meter", "key", "metadata"] + [f"tracks.{i}" for i in range(3) if i != track_index]
        return RostrumTask(task_id, "L0", f"Mute track '{track_id}'. Do not modify any other track or project setting.", project,
            ["inspect_project", "mute_track"],
            [{"type": "project_property", "path": f"tracks.{track_index}.muted", "equals": True},
             {"type": "preserve_paths", "paths": preserve}],
            ["mechanics", "track-state", "procedural"])

    target_gain = float(rng.choice([-9, -6, -3, 3, 6]))
    preserve = ["tempo", "meter", "key", "metadata"] + [f"tracks.{i}" for i in range(3) if i != track_index]
    return RostrumTask(task_id, "L0", f"Set track '{track_id}' gain to {target_gain:g} dB. Do not modify anything else.", project,
        ["inspect_project", "set_track_gain"],
        [{"type": "project_property", "path": f"tracks.{track_index}.gain_db", "equals": target_gain},
         {"type": "preserve_paths", "paths": preserve}],
        ["mechanics", "gain", "procedural"])


def generate_suite(count: int = 100, seed: int = 20260808) -> list[RostrumTask]:
    master = random.Random(seed)
    return [generate_task(index, master.randrange(0, 2**31)) for index in range(count)]


def write_suite(output: str | Path, count: int = 100, seed: int = 20260808) -> list[Path]:
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for task in generate_suite(count=count, seed=seed):
        path = directory / f"{task.id}.json"
        path.write_text(json.dumps(task.to_dict(), indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic Composer Rostrum tasks")
    parser.add_argument("output", help="Directory for generated task JSON files")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260808)
    args = parser.parse_args()
    paths = write_suite(args.output, count=args.count, seed=args.seed)
    print(f"wrote {len(paths)} tasks to {Path(args.output)}")


if __name__ == "__main__":
    main()
