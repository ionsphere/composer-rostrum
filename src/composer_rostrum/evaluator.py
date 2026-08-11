from __future__ import annotations

from typing import Any

from .models import EvaluationResult, MusicProject, RostrumTask
from .music_theory import scale_pitch_classes, triad_pitch_classes


def _read_path(project: MusicProject, path: str) -> Any:
    value: Any = project.to_dict()
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _notes(project: MusicProject, track_id: str, clip_id: str) -> list[dict[str, Any]]:
    track = next(track for track in project.tracks if track.get("id") == track_id)
    clip = next(clip for clip in track.get("clips", []) if clip.get("id") == clip_id)
    return clip.get("notes", [])


def evaluate(task: RostrumTask, before: MusicProject, after: MusicProject) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []

    for spec in task.evaluators:
        evaluator_type = spec["type"]

        if evaluator_type == "project_property":
            actual = _read_path(after, spec["path"]); expected = spec["equals"]
            passed = actual == expected
            results.append(EvaluationResult(f"project_property:{spec['path']}", passed, 1.0 if passed else 0.0,
                f"expected {expected!r}, got {actual!r}")); continue

        if evaluator_type == "preserve_paths":
            changed = [path for path in spec["paths"] if _read_path(before, path) != _read_path(after, path)]
            passed = not changed
            results.append(EvaluationResult("preserve_paths", passed, 1.0 if passed else 0.0,
                "preserved" if passed else f"unexpected changes: {', '.join(changed)}")); continue

        if evaluator_type == "notes_quantized":
            notes = _notes(after, spec["track_id"], spec["clip_id"]); grid = float(spec["grid"])
            bad = [note["id"] for note in notes if abs(float(note["start"]) / grid - round(float(note["start"]) / grid)) > 1e-9]
            passed = not bad
            results.append(EvaluationResult("notes_quantized", passed, 1.0 if passed else 0.0,
                "all notes quantized" if passed else f"off-grid notes: {bad}")); continue

        if evaluator_type == "notes_in_scale":
            notes = _notes(after, spec["track_id"], spec["clip_id"]); allowed = scale_pitch_classes(spec["key"])
            bad = [note["id"] for note in notes if int(note["pitch"]) % 12 not in allowed]
            passed = not bad
            results.append(EvaluationResult("notes_in_scale", passed, 1.0 if passed else 0.0,
                "all notes in scale" if passed else f"out-of-scale notes: {bad}")); continue

        if evaluator_type == "triad_pitch_classes":
            notes = _notes(after, spec["track_id"], spec["clip_id"])
            actual = {int(note["pitch"]) % 12 for note in notes}; expected = triad_pitch_classes(spec["chord"])
            passed = actual == expected
            results.append(EvaluationResult("triad_pitch_classes", passed, 1.0 if passed else 0.0,
                f"expected pitch classes {sorted(expected)}, got {sorted(actual)}")); continue

        if evaluator_type == "changed_note_count":
            before_notes = {note["id"]: note for note in _notes(before, spec["track_id"], spec["clip_id"])}
            after_notes = {note["id"]: note for note in _notes(after, spec["track_id"], spec["clip_id"])}
            changed = [note_id for note_id in before_notes if before_notes[note_id] != after_notes.get(note_id)]
            expected = int(spec["equals"]); passed = len(changed) == expected
            results.append(EvaluationResult("changed_note_count", passed, 1.0 if passed else 0.0,
                f"expected {expected} changed notes, got {len(changed)}: {changed}")); continue

        results.append(EvaluationResult(evaluator_type, False, 0.0, "evaluator type is not implemented yet"))

    return results


def aggregate_score(results: list[EvaluationResult]) -> float:
    if not results: return 0.0
    return sum(result.score for result in results) / len(results)
