from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from composer_rostrum.backends.base import BackendError
from composer_rostrum.backends.reaper import ReaperBackend
from composer_rostrum.corpus import generate_chains
from composer_rostrum.environment import MusicEnvironment, ToolError, project_hash
from composer_rostrum.evaluator import evaluate
from composer_rostrum.models import MusicProject


def test_corpus_is_reproducible_unique_and_split_by_chain():
    first, second = generate_chains(), generate_chains()
    assert [[s.task.to_dict() for s in c.steps] for c in first] == [[s.task.to_dict() for s in c.steps] for c in second]
    assert len(first) == 40 and sum(len(c.steps) for c in first) == 240
    assert len({project_hash(c.steps[0].expected) for c in first}) == 40
    assert {split: sum(c.split == split for c in first) for split in ("train", "dev", "test")} == {"train": 24, "dev": 8, "test": 8}
    for chain in first:
        assert all(s.task.tags[-1] == chain.split for s in chain.steps)
        for before, after in zip(chain.steps, chain.steps[1:]):
            assert project_hash(before.expected) == project_hash(after.task.initial_project)


def test_all_exact_reference_edits_pass_and_negative_controls_fail():
    for chain in generate_chains():
        for step in chain.steps:
            ReaperBackend.validate(step.task.initial_project)
            if step.expected is None:
                continue
            env = MusicEnvironment(step.task.initial_project, step.task.allowed_tools)
            for op in step.operations:
                env.call(op["tool"], **op["arguments"])
            ReaperBackend.validate(env.project)
            assert env.project.to_dict() == step.expected.to_dict()
            assert all(r.passed for r in evaluate(step.task, step.task.initial_project, env.project))
            assert not all(r.passed for r in evaluate(step.task, step.task.initial_project, step.task.initial_project))
            damaged = env.project
            damaged.meter = "3/4"
            assert not all(r.passed for r in evaluate(step.task, step.task.initial_project, damaged))


def test_wrong_fade_and_wrong_note_are_rejected_even_with_other_changes_correct():
    chain = generate_chains(1)[0]
    for index, mutation in [(1, lambda p: p.tracks[0]["clips"][0]["notes"][0].update(pitch=1)),
                             (2, lambda p: p.tracks[1]["clips"][0].update(fade_in_seconds=0.0))]:
        step = chain.steps[index]
        damaged = deepcopy(step.expected)
        mutation(damaged)
        assert not all(r.passed for r in evaluate(step.task, step.task.initial_project, damaged))


@pytest.mark.parametrize("fade", [-1, float("nan"), float("inf"), 3])
def test_invalid_fades_cannot_mutate_project(fade):
    project = generate_chains(1)[0].steps[0].expected
    env = MusicEnvironment(project, ["set_clip_fades"])
    with pytest.raises(ToolError):
        env.call("set_clip_fades", track_id="samples", clip_id="hit", fade_in_seconds=fade, fade_out_seconds=0.1)
    assert project_hash(env.project) == project_hash(project)
    project.tracks[1]["clips"][0]["fade_in_seconds"] = fade
    with pytest.raises(BackendError, match="fade lengths"):
        ReaperBackend.validate(project)


def test_creation_rejects_duplicate_ids_and_incompatible_track_without_mutating():
    env = MusicEnvironment(MusicProject(), ["add_track", "add_audio_clip", "add_midi_clip"])
    env.call("add_track", track_id="audio", name="Audio", kind="audio")
    before = project_hash(env.project)
    with pytest.raises(ToolError, match="duplicate"):
        env.call("add_track", track_id="audio", name="Audio", kind="audio")
    with pytest.raises(ToolError, match="kind"):
        env.call("add_midi_clip", track_id="audio", clip_id="midi", start=0, length=4, notes=[])
    assert project_hash(env.project) == before


def test_snapshot_tampering_fails_before_reaper_is_launched(tmp_path):
    from composer_rostrum.corpus_capture import verify_snapshot
    (tmp_path / "project.rpp").write_text("tampered")
    (tmp_path / "state.json").write_text(json.dumps({"files": {"project.rpp": "wrong"}}))
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_snapshot(tmp_path, tmp_path / "worker", "missing.exe")


def test_resume_rejects_mismatched_specifications(tmp_path):
    from composer_rostrum.corpus_capture import _cached_chain, write_json
    chain = generate_chains(1)[0]
    step = chain.steps[0]
    assert _cached_chain(tmp_path, chain) is None
    write_json(tmp_path / "inputs" / f"{step.task.id}.json", {"prompt": "wrong prompt"})
    write_json(tmp_path / "private" / f"{step.task.id}.json", {"task": step.task.to_dict()})
    with pytest.raises(ValueError, match="different task specifications"):
        _cached_chain(tmp_path, chain)


def test_snapshot_manifest_cannot_reference_files_outside_its_directory(tmp_path):
    from composer_rostrum.corpus_capture import sha256, verify_snapshot, write_json
    state = tmp_path / "state"
    secret = tmp_path / "unrelated"
    secret.write_text("not a snapshot artifact")
    write_json(state / "state.json", {"files": {"../unrelated": sha256(secret)}})
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_snapshot(state, tmp_path / "worker", "missing.exe")


def test_frozen_corpus_prompts_and_task_hashes():
    manifest = json.loads((Path(__file__).parents[1] / "benchmarks/reaper-chains-v1.json").read_text(encoding="utf-8"))
    generated = []
    for chain in generate_chains(manifest["chains"], manifest["seed"]):
        for step in chain.steps:
            payload = json.dumps(step.task.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            generated.append({"id": step.task.id, "chain_id": chain.id, "split": chain.split,
                "stage": step.task.tags[1], "prompt": step.task.prompt, "task_sha256": hashlib.sha256(payload).hexdigest()})
    assert manifest["samples"] == generated
