from __future__ import annotations

from typing import Any

from .models import EvaluationResult, MusicProject, RostrumTask
from .music_theory import scale_pitch_classes, triad_pitch_classes


def _read_path(project: MusicProject, path: str) -> Any:
    value: Any = project.to_dict()
    for part in path.split("."): value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _clip(project: MusicProject, track_id: str, clip_id: str) -> dict[str, Any]:
    track = next(track for track in project.tracks if track.get("id") == track_id)
    return next(clip for clip in track.get("clips", []) if clip.get("id") == clip_id)


def _notes(project: MusicProject, track_id: str, clip_id: str) -> list[dict[str, Any]]:
    return _clip(project, track_id, clip_id).get("notes", [])


def _note(project: MusicProject, track_id: str, clip_id: str, note_id: str) -> dict[str, Any]:
    return next(note for note in _notes(project, track_id, clip_id) if note.get("id") == note_id)


def evaluate(task: RostrumTask, before: MusicProject, after: MusicProject) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for spec in task.evaluators:
        t = spec["type"]
        if t == "project_property":
            actual = _read_path(after, spec["path"]); expected = spec["equals"]; passed = actual == expected
            results.append(EvaluationResult(f"project_property:{spec['path']}", passed, float(passed), f"expected {expected!r}, got {actual!r}")); continue
        if t == "preserve_paths":
            changed = [p for p in spec["paths"] if _read_path(before, p) != _read_path(after, p)]; passed = not changed
            results.append(EvaluationResult("preserve_paths", passed, float(passed), "preserved" if passed else f"unexpected changes: {', '.join(changed)}")); continue
        if t == "notes_quantized":
            notes = _notes(after, spec["track_id"], spec["clip_id"]); grid = float(spec["grid"])
            bad = [n["id"] for n in notes if abs(float(n["start"]) / grid - round(float(n["start"]) / grid)) > 1e-9]; passed = not bad
            results.append(EvaluationResult("notes_quantized", passed, float(passed), "all notes quantized" if passed else f"off-grid notes: {bad}")); continue
        if t == "note_quantized":
            n = _note(after, spec["track_id"], spec["clip_id"], spec["note_id"]); grid = float(spec["grid"])
            passed = abs(float(n["start"]) / grid - round(float(n["start"]) / grid)) <= 1e-9
            results.append(EvaluationResult("note_quantized", passed, float(passed), f"note start={n['start']} grid={grid}")); continue
        if t == "notes_in_scale":
            notes = _notes(after, spec["track_id"], spec["clip_id"]); allowed = scale_pitch_classes(spec["key"])
            bad = [n["id"] for n in notes if int(n["pitch"]) % 12 not in allowed]; passed = not bad
            results.append(EvaluationResult("notes_in_scale", passed, float(passed), "all notes in scale" if passed else f"out-of-scale notes: {bad}")); continue
        if t == "note_in_chord":
            n = _note(after, spec["track_id"], spec["clip_id"], spec["note_id"]); allowed = triad_pitch_classes(spec["chord"])
            passed = int(n["pitch"]) % 12 in allowed
            results.append(EvaluationResult("note_in_chord", passed, float(passed), f"pitch={n['pitch']} allowed={sorted(allowed)}")); continue
        if t == "triad_pitch_classes":
            notes = _notes(after, spec["track_id"], spec["clip_id"]); actual = {int(n["pitch"]) % 12 for n in notes}; expected = triad_pitch_classes(spec["chord"]); passed = actual == expected
            results.append(EvaluationResult("triad_pitch_classes", passed, float(passed), f"expected pitch classes {sorted(expected)}, got {sorted(actual)}")); continue
        if t == "changed_note_count":
            b = {n["id"]: n for n in _notes(before, spec["track_id"], spec["clip_id"])}; a = {n["id"]: n for n in _notes(after, spec["track_id"], spec["clip_id"])}
            changed = [nid for nid in b if b[nid] != a.get(nid)]; expected = int(spec["equals"]); passed = len(changed) == expected
            results.append(EvaluationResult("changed_note_count", passed, float(passed), f"expected {expected} changed notes, got {len(changed)}: {changed}")); continue
        if t == "clip_transposition_relation":
            source = _clip(after, spec["track_id"], spec["source_clip_id"]); target = _clip(after, spec["track_id"], spec["target_clip_id"]); delta = int(spec["semitones"])
            s_notes = source.get("notes", []); t_notes = target.get("notes", [])
            same_shape = len(s_notes) == len(t_notes) and all(int(tn["pitch"]) == int(sn["pitch"]) + delta and float(tn["start"]) == float(sn["start"]) and float(tn["duration"]) == float(sn["duration"]) and int(tn["velocity"]) == int(sn["velocity"]) for sn, tn in zip(s_notes, t_notes))
            passed = same_shape and float(target.get("start", -1)) == float(spec["target_start"])
            results.append(EvaluationResult("clip_transposition_relation", passed, float(passed), "response matches transformed source" if passed else "response does not match requested relation")); continue
        if t == "all_notes_transposed_from_repaired_triad":
            notes = _notes(after, spec["track_id"], spec["clip_id"]); delta = int(spec["semitones"]); expected = triad_pitch_classes(spec["chord"])
            actual_down = {(int(n["pitch"]) - delta) % 12 for n in notes}; in_range = all(int(n["pitch"]) - delta >= 0 for n in notes); passed = actual_down == expected and in_range
            results.append(EvaluationResult("all_notes_transposed_from_repaired_triad", passed, float(passed), f"expected repaired pitch classes {sorted(expected)}, got {sorted(actual_down)} after reversing transpose")); continue
        results.append(EvaluationResult(t, False, 0.0, "evaluator type is not implemented yet"))
    return results


def aggregate_score(results: list[EvaluationResult]) -> float:
    return 0.0 if not results else sum(r.score for r in results) / len(results)
