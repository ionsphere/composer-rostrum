from copy import deepcopy

from composer_rostrum.environment import MusicEnvironment
from composer_rostrum.evaluator import evaluate
from composer_rostrum.multistep_generator import generate_multistep_suite
from composer_rostrum.runner import run_task


def test_multistep_suite_is_deterministic_and_unique():
    first = generate_multistep_suite()
    second = generate_multistep_suite()
    assert [task.to_dict() for task in first] == [task.to_dict() for task in second]
    assert len(first) == 48
    assert len({task.id for task in first}) == 48
    assert {task.tags[1] for task in first} >= {"bass", "arrangement", "harmony"}


def test_reference_agent_solves_multistep_suite_with_real_depth():
    outcomes = [run_task(task) for task in generate_multistep_suite()]
    failures = [outcome["task_id"] for outcome in outcomes if not outcome["passed"]]
    assert failures == []
    assert all(outcome["tool_calls"] >= 3 for outcome in outcomes)  # inspect + at least two edits


def test_duplicate_transform_preserves_source_clip():
    task = next(task for task in generate_multistep_suite() if "arrangement" in task.tags)
    before = deepcopy(task.initial_project)
    outcome = run_task(task)
    assert outcome["passed"] is True
    assert outcome["project"]["tracks"][0]["clips"][0] == before.tracks[0]["clips"][0]
    assert len(outcome["project"]["tracks"][0]["clips"]) == 2


def test_relational_evaluator_rejects_wrong_response_even_if_clip_exists():
    task = next(task for task in generate_multistep_suite() if "arrangement" in task.tags)
    before = deepcopy(task.initial_project)
    environment = MusicEnvironment(before, task.allowed_tools)
    environment.call("duplicate_clip", track_id="keys", source_clip_id="call", new_clip_id="response", start=4.0)
    results = evaluate(task, before, environment.project)
    relation = next(result for result in results if result.evaluator == "clip_transposition_relation")
    assert relation.passed is False
