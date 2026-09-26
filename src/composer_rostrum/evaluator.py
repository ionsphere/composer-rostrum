from __future__ import annotations

from typing import Any

from .models import EvaluationResult, MusicProject, RostrumTask
from .music_theory import scale_pitch_classes, triad_pitch_classes
from .environment import _diff_paths


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


def _evaluate_specs(task: RostrumTask, before: MusicProject, after: MusicProject) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for spec in task.evaluators:
        t = spec["type"]
        if t in {"render_valid", "render_rms_target", "feedback_improvement"}:
            continue
        if t == "preserve_except":
            changed = _diff_paths(before.to_dict(), after.to_dict())
            bad = [p for p in changed if not any(p == allow or p.startswith(allow + ".") for allow in spec["paths"])]
            results.append(EvaluationResult(t, not bad, float(not bad), f"unexpected changes: {bad}" if bad else "protected state preserved"))
            continue
        if t == "project_property":
            actual = _read_path(after, spec["path"]); expected = spec["equals"]; passed = actual == expected
            results.append(EvaluationResult(f"project_property:{spec['path']}", passed, float(passed), f"expected {expected!r}, got {actual!r}")); continue
        if t == "rhythm_pattern":
            track = next(track for track in after.tracks if track["id"] == spec["track_id"])
            ids = spec["clip_ids"]
            clips = track.get("clips", [])
            selected = [next(clip for clip in clips if clip["id"] == identity) for identity in ids]
            actual = [float(clip["timeline_start_beats"]) for clip in selected]
            expected = [float(value) for value in spec["onsets_beats"]]
            tolerance = float(spec.get("tolerance_beats", 1/960))
            passed = (len(ids) == len(expected) and len(clips) == len(ids) and
                      len(set(ids)) == len(ids) and
                      all(abs(x-y) <= tolerance for x, y in zip(actual, expected)))
            results.append(EvaluationResult(t, passed, float(passed),
                f"{spec['track_id']} onsets expected={expected}, actual={actual}, tolerance={tolerance}")); continue
        if t == "track_alignment":
            left = [_clip(after, spec["left_track_id"], identity) for identity in spec["left_clip_ids"]]
            right = [_clip(after, spec["right_track_id"], identity) for identity in spec["right_clip_ids"]]
            offset = float(spec.get("offset_beats", 0))
            tolerance = float(spec.get("tolerance_beats", 1/960))
            differences = [float(b["timeline_start_beats"])-float(a["timeline_start_beats"])
                           for a, b in zip(left, right)]
            passed = (len(left) == len(right) and len(left) > 0 and
                      all(abs(delta-offset) <= tolerance for delta in differences))
            results.append(EvaluationResult(t, passed, float(passed),
                f"pairwise offsets expected={offset}, actual={differences}, tolerance={tolerance}")); continue
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
            changed = [nid for nid in set(b) | set(a) if b.get(nid) != a.get(nid)]; expected = int(spec["equals"]); passed = len(changed) == expected
            results.append(EvaluationResult("changed_note_count", passed, float(passed), f"expected {expected} changed notes, got {len(changed)}: {changed}")); continue
        if t == "clip_transposition_relation":
            source = _clip(after, spec["track_id"], spec["source_clip_id"]); target = _clip(after, spec["track_id"], spec["target_clip_id"]); delta = int(spec["semitones"])
            s_notes = source.get("notes", []); t_notes = target.get("notes", [])
            same_shape = len(s_notes) == len(t_notes) and all(int(tn["pitch"]) == int(sn["pitch"]) + delta and float(tn["start"]) == float(sn["start"]) and float(tn["duration"]) == float(sn["duration"]) and int(tn["velocity"]) == int(sn["velocity"]) for sn, tn in zip(s_notes, t_notes))
            passed = same_shape and float(target.get("start", -1)) == float(spec["target_start"])
            results.append(EvaluationResult("clip_transposition_relation", passed, float(passed), "response matches transformed source" if passed else "response does not match requested relation")); continue
        if t == "all_notes_transposed_from_repaired_triad":
            old = _notes(before, spec["track_id"], spec["clip_id"])
            notes = _notes(after, spec["track_id"], spec["clip_id"])
            delta = int(spec["semitones"]); pcs = triad_pitch_classes(spec["chord"])
            present = {int(n["pitch"]) % 12 for n in old}; missing = pcs - present
            expected = {}
            for n in old:
                pitch = int(n["pitch"])
                if pitch % 12 not in pcs and len(missing) == 1:
                    pc = next(iter(missing))
                    pitch = min((p for p in range(128) if p % 12 == pc), key=lambda p: (abs(p-pitch), p))
                expected[n["id"]] = {**n, "pitch": pitch + delta}
            passed = len(notes) == len(old) and {n["id"]: n for n in notes} == expected
            results.append(EvaluationResult(t, passed, float(passed), "checked repaired pitches, octave, identity and rhythm")); continue
        results.append(EvaluationResult(t, False, 0.0, "evaluator type is not implemented yet"))
    return results


def aggregate_score(results: list[EvaluationResult]) -> float:
    return 0.0 if not results else sum(r.score for r in results) / len(results)


def evaluate(task: RostrumTask, before: MusicProject, after: MusicProject) -> list[EvaluationResult]:
    from dataclasses import replace
    results = []
    for spec in task.evaluators:
        try:
            results.extend(_evaluate_specs(replace(task, evaluators=[spec]), before, after))
        except (KeyError, IndexError, StopIteration, TypeError, ValueError) as exc:
            results.append(EvaluationResult(spec.get("type", "invalid"), False, 0.0,
                           f"required project structure is missing or invalid ({type(exc).__name__})"))
    return results
