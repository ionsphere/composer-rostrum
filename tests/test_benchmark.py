from copy import deepcopy
from collections import Counter

from composer_rostrum.benchmark import generate_benchmark, fingerprint, NoOpAgent, DamagingAgent, summarize
from composer_rostrum.environment import project_hash, _diff_paths
from composer_rostrum.models import MusicProject
from composer_rostrum.runner import run_task
from composer_rostrum.evaluator import evaluate
from composer_rostrum.multistep_generator import generate_multistep_task


def test_frozen_splits_are_reproducible_unique_and_balanced():
    a, b = generate_benchmark(), generate_benchmark()
    assert {k: [t.to_dict() for t in v] for k, v in a.items()} == {k: [t.to_dict() for t in v] for k, v in b.items()}
    assert {k: len(v) for k, v in a.items()} == {"train": 72, "dev": 24, "test": 24}
    fingerprints = [fingerprint(t) for tasks in a.values() for t in tasks]
    assert len(set(fingerprints)) == 120
    assert set(Counter(t.initial_project.metadata["family"] for tasks in a.values() for t in tasks).values()) == {10}


def test_all_reference_and_negative_controls():
    for tasks in generate_benchmark().values():
        for task in tasks:
            assert run_task(task)["passed"], task.id
            assert not run_task(task, NoOpAgent())["passed"], task.id
            assert not run_task(task, DamagingAgent())["passed"], task.id


def test_agent_cannot_see_or_mutate_evaluators():
    class Curious:
        def solve(self, task, environment):
            assert task.evaluators == []
            task.evaluators.append({"type": "anything"})
    task = generate_benchmark()["test"][0]
    original = deepcopy(task.to_dict())
    assert not run_task(task, Curious())["passed"]
    assert task.to_dict() == original


def test_transpose_evaluator_rejects_repair_without_octave_change():
    from composer_rostrum.agent import ReferenceAgent
    from composer_rostrum.environment import MusicEnvironment
    task = generate_multistep_task(2, 47)
    env = MusicEnvironment(task.initial_project, task.allowed_tools)
    ReferenceAgent().solve(task, env)
    after = env.project
    for note in after.tracks[0]["clips"][0]["notes"]:
        note["pitch"] -= 12
    assert not all(r.passed for r in evaluate(task, task.initial_project, after))


def test_missing_target_is_a_failed_score_not_an_evaluator_crash():
    task = generate_multistep_task(1, 123)
    assert not all(r.passed for r in evaluate(task, task.initial_project, MusicProject()))


def test_native_numeric_serialization_is_semantically_equivalent():
    a = MusicProject(tracks=[{"gain_db": 0.0}])
    b = MusicProject(tracks=[{"gain_db": 0}])
    assert project_hash(a) == project_hash(b)
    assert _diff_paths(a.to_dict(), b.to_dict()) == []
    assert _diff_paths(False, 0) == ["$root"]


def test_infrastructure_is_excluded_from_agent_pass_rate():
    rows = [{"passed": True, "infrastructure": {"ok": True}},
            {"passed": False, "infrastructure": {"ok": False}, "failure_class": "infrastructure"}]
    report = summarize(rows)
    assert report["pass_rate"] == 1
    assert report["tasks"] == 2 and report["infrastructure_failures"] == 1


def test_written_manifest_hashes_match_actual_bytes(tmp_path):
    import hashlib
    from composer_rostrum.benchmark import write_benchmark
    directory = tmp_path / "benchmark"
    manifest = write_benchmark(directory)
    for row in manifest["tasks"]:
        raw = (directory / row["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
        assert b"\r\n" not in raw
        assert (directory / "oracles" / f"{row['id']}.json").exists()


def test_frozen_manifest_guards_dataset_version():
    import hashlib
    import json
    from pathlib import Path
    manifest = json.loads((Path(__file__).parents[1] / "benchmarks/rostrum-120-v1.json").read_text(encoding="utf-8"))
    rows = {row["id"]: row for row in manifest["tasks"]}
    for split, tasks in generate_benchmark(manifest["seed"]).items():
        for task in tasks:
            content = json.dumps(task.to_dict(), indent=2) + "\n"
            assert rows[task.id]["sha256"] == hashlib.sha256(content.encode()).hexdigest()
            assert rows[task.id]["split"] == split
