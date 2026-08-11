from __future__ import annotations

NOTE_TO_PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
SCALE_INTERVALS = {"major": (0, 2, 4, 5, 7, 9, 11), "minor": (0, 2, 3, 5, 7, 8, 10)}
TRIAD_INTERVALS = {"major": (0, 4, 7), "minor": (0, 3, 7)}


def parse_key(label: str) -> tuple[int, str]:
    root, quality = label.split("_", 1)
    if root not in NOTE_TO_PC or quality not in SCALE_INTERVALS:
        raise ValueError(f"unsupported key {label!r}")
    return NOTE_TO_PC[root], quality


def scale_pitch_classes(label: str) -> set[int]:
    root, quality = parse_key(label)
    return {(root + interval) % 12 for interval in SCALE_INTERVALS[quality]}


def triad_pitch_classes(label: str) -> set[int]:
    root, quality = parse_key(label)
    return {(root + interval) % 12 for interval in TRIAD_INTERVALS[quality]}


def nearest_pitch_in_scale(pitch: int, label: str) -> int:
    pcs = scale_pitch_classes(label)
    candidates = [candidate for candidate in range(max(0, pitch - 6), min(127, pitch + 6) + 1) if candidate % 12 in pcs]
    return min(candidates, key=lambda candidate: (abs(candidate - pitch), candidate))
