import pytest

from composer_rostrum.environment import MusicEnvironment, ToolError
from composer_rostrum.generator import generate_suite
from composer_rostrum.models import MusicProject
from composer_rostrum.runner import load_task, run_task


def test_seed_task_passes_through_environment():
    task = load_task("examples/tasks/L0-001-set-tempo.json")
    outcome = run_task(task)
    assert outcome["passed"] is True
    assert outcome["score"] == 1.0
    assert outcome["project"]["tempo"] == 128.0
    assert [event["tool"] for event in outcome["trajectory"]] == ["inspect_project", "set_tempo"]
    assert outcome["trajectory"][1]["changed_paths"] == ["tempo"]


def test_environment_blocks_direct_state_mutation_and_disallowed_tools():
    project = MusicProject(tempo=120)
    environment = MusicEnvironment(project, ["inspect_project"])
    copy = environment.project
    copy.tempo = 42
    assert environment.project.tempo == 120
    with pytest.raises(ToolError):
        environment.call("set_tempo", bpm=128)


def test_rostrum_100_is_deterministic_unique_and_reference_solvable():
    first = generate_suite()
    second = generate_suite()
    assert [task.to_dict() for task in first] == [task.to_dict() for task in second]
    assert len(first) == 100
    assert len({task.id for task in first}) == 100
    outcomes = [run_task(task) for task in first]
    assert all(outcome["passed"] for outcome in outcomes)
    assert all(outcome["trajectory"] for outcome in outcomes)
