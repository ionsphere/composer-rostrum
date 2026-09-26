import json

import pytest

from composer_rostrum.corpus import generate_chains
from composer_rostrum.corpus_capture import sha256, write_json
from composer_rostrum.corpus_eval import (dataset_path, load_sample, reference_audio_path,
                                         production_audio_expectation)
from composer_rostrum.environment import project_hash


def fixture_dataset(root):
    task = generate_chains(1)[0].steps[1].task
    state = root / "states/input"
    write_json(state / "project.music-ir.json", task.initial_project.to_dict())
    (state / "project.rpp").write_text("native-test-placeholder")
    write_json(state / "state.json", {"project_hash": project_hash(task.initial_project),
        "files": {p.name: sha256(p) for p in state.iterdir()}})
    write_json(root / "inputs/sample.json", {"id": task.id, "prompt": task.prompt,
        "allowed_tools": task.allowed_tools, "input_state": "states/input", "split": "train"})
    write_json(root / "private/sample.json", {"task": task.to_dict()})
    (root / "samples.jsonl").write_text(json.dumps({"id": task.id, "input": "inputs/sample.json", "private_target": "private/sample.json"}) + "\n")
    write_json(root / "checksums.json", {p.relative_to(root).as_posix(): sha256(p) for p in root.rglob("*") if p.is_file()})
    return task.id


def test_eval_loader_checks_prompt_state_and_inventory(tmp_path):
    identity = fixture_dataset(tmp_path)
    task, public, state = load_sample(tmp_path, identity)
    assert task.id == identity and task.evaluators
    assert "evaluators" not in public and "target_state" not in public
    assert state == tmp_path / "states/input"
    (state / "project.rpp").write_text("changed native input")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_sample(tmp_path, identity)


def test_eval_loader_rejects_mismatched_public_prompt_even_if_rehashed(tmp_path):
    identity = fixture_dataset(tmp_path)
    path = tmp_path / "inputs/sample.json"
    public = json.loads(path.read_text())
    public["prompt"] = "Different request"
    write_json(path, public)
    manifest = json.loads((tmp_path / "checksums.json").read_text())
    manifest["inputs/sample.json"] = sha256(path)
    write_json(tmp_path / "checksums.json", manifest)
    with pytest.raises(ValueError, match="public task differs"):
        load_sample(tmp_path, identity)


def test_dataset_paths_cannot_escape_root(tmp_path):
    with pytest.raises(ValueError, match="escapes"):
        dataset_path(tmp_path, "../private-file")


def test_unknown_sample_is_an_error(tmp_path):
    fixture_dataset(tmp_path)
    with pytest.raises(ValueError, match="exactly one"):
        load_sample(tmp_path, "missing")


def test_reference_audio_stays_private_and_checksum_checked(tmp_path):
    identity = fixture_dataset(tmp_path)
    private_file = tmp_path / "private/sample.json"
    private = json.loads(private_file.read_text())
    private["target_state"] = "states/target"
    write_json(private_file, private)
    target = tmp_path / "states/target/render.wav"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"reference audio")
    inventory = json.loads((tmp_path / "checksums.json").read_text())
    inventory["private/sample.json"] = sha256(private_file)
    inventory["states/target/render.wav"] = sha256(target)
    write_json(tmp_path / "checksums.json", inventory)
    assert reference_audio_path(tmp_path, identity) == target
    target.write_bytes(b"tampered audio")
    with pytest.raises(ValueError, match="target audio checksum mismatch"):
        reference_audio_path(tmp_path, identity)


def test_production_rule_is_private_and_checksum_checked(tmp_path):
    identity = fixture_dataset(tmp_path)
    private_file = tmp_path / "private/sample.json"
    private = json.loads(private_file.read_text())
    private["audio_expectation"] = {"kind": "clip_gain", "clips": []}
    write_json(private_file, private)
    inventory = json.loads((tmp_path / "checksums.json").read_text())
    inventory["private/sample.json"] = sha256(private_file)
    write_json(tmp_path / "checksums.json", inventory)
    assert production_audio_expectation(tmp_path, identity) == private["audio_expectation"]
    private["audio_expectation"]["kind"] = "same"
    write_json(private_file, private)
    with pytest.raises(ValueError, match="private scoring specification checksum mismatch"):
        production_audio_expectation(tmp_path, identity)
