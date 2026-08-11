from copy import deepcopy

from composer_rostrum.environment import MusicEnvironment
from composer_rostrum.runner import run_task
from composer_rostrum.symbolic_generator import generate_symbolic_suite


def test_symbolic_suite_is_deterministic_and_unique():
    first = generate_symbolic_suite()
    second = generate_symbolic_suite()
    assert [task.to_dict() for task in first] == [task.to_dict() for task in second]
    assert len(first) == 80
    assert len({task.id for task in first}) == 80
    assert {task.tags[1] for task in first} >= {"transposition", "rhythm", "harmony", "scale"}


def test_reference_agent_solves_symbolic_suite():
    outcomes = [run_task(task) for task in generate_symbolic_suite()]
    failures = [outcome["task_id"] for outcome in outcomes if not outcome["passed"]]
    assert failures == []


def test_environment_logs_note_edits_without_direct_mutation():
    task = generate_symbolic_suite(count=1)[0]
    environment = MusicEnvironment(task.initial_project, task.allowed_tools)
    detached = environment.project
    detached.tracks[0]["clips"][0]["notes"][0]["pitch"] = 1
    assert environment.project.tracks[0]["clips"][0]["notes"][0]["pitch"] != 1

    environment.call("inspect_project")
    environment.call("transpose_notes", track_id="keys", clip_id="phrase", semitones=2)
    edit = environment.trajectory[-1]
    assert edit.tool == "transpose_notes"
    assert any("notes" in path and "pitch" in path for path in edit.changed_paths)


def test_chord_repair_requires_minimal_edit():
    task = next(task for task in generate_symbolic_suite() if "harmony" in task.tags)
    before = deepcopy(task.initial_project)
    environment = MusicEnvironment(before, task.allowed_tools)
    notes = environment.call("inspect_project")["tracks"][0]["clips"][0]["notes"]
    environment.call("set_note_pitch", track_id="keys", clip_id="phrase", note_id=notes[0]["id"], pitch=notes[0]["pitch"] + 12)
    environment.call("set_note_pitch", track_id="keys", clip_id="phrase", note_id=notes[1]["id"], pitch=notes[1]["pitch"] + 12)

    from composer_rostrum.evaluator import evaluate
    results = evaluate(task, before, environment.project)
    minimal = next(result for result in results if result.evaluator == "changed_note_count")
    assert minimal.passed is False
