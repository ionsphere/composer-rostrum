import pytest
import wave
import hashlib
import json
from pathlib import Path

from composer_rostrum.environment import MusicEnvironment, ToolError
from composer_rostrum.item_edit_corpus import generate_item_edit_chains
from composer_rostrum.corpus_capture import _stable_ids, pcm_equivalent


def test_item_edit_chains_link_states_and_splits():
    chains = generate_item_edit_chains(20)
    assert len(chains) == 20
    assert {c.split for c in chains} == {"train", "dev", "test"}
    for chain in chains:
        assert [step.task.tags[1] for step in chain.steps] == ["split", "move"]
        assert chain.steps[1].task.initial_project.to_dict() == chain.steps[0].expected.to_dict()
        left, right = chain.steps[0].expected.tracks[0]["clips"]
        assert left["source_end"] == right["source_start"]
        assert left["id"] == "hit" and right["id"] == "tail"
        assert chain.steps[1].expected.tracks[0]["clips"][0] == left
        assert chain.steps[1].expected.tracks[0]["clips"][1]["timeline_start_beats"] > right["timeline_start_beats"]


def test_split_rejects_invalid_point_and_preserves_state():
    project = generate_item_edit_chains(1)[0].steps[0].task.initial_project
    env = MusicEnvironment(project, ["split_audio_clip"])
    for point in (-1, 0, 2, float("nan")):
        with pytest.raises(ToolError):
            env.call("split_audio_clip", track_id="samples", clip_id="hit", new_clip_id="tail", source_seconds=point)
        assert env.project.to_dict() == project.to_dict()


def test_existing_guids_must_survive_new_item():
    before = {"samples": {"guid": "track-1", "items": {"hit": "item-1"}}}
    after = {"samples": {"guid": "track-1", "items": {"hit": "item-1", "tail": "item-2"}}}
    assert _stable_ids(before, after)
    after["samples"]["items"]["hit"] = "item-3"
    assert not _stable_ids(before, after)


def test_pcm_equivalence_only_allows_sparse_one_lsb_rounding(tmp_path):
    def write(path, data):
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(3)
            output.setframerate(48000)
            output.writeframes(b"".join(value.to_bytes(3, "little", signed=True) for value in data))

    original = [100] * 20000
    write(tmp_path / "a.wav", original)
    slight = original.copy()
    slight[100] += 1
    write(tmp_path / "b.wav", slight)
    assert not pcm_equivalent(tmp_path / "a.wav", tmp_path / "b.wav")
    assert pcm_equivalent(tmp_path / "a.wav", tmp_path / "b.wav", 1)
    slight[101] += 2
    write(tmp_path / "b.wav", slight)
    assert not pcm_equivalent(tmp_path / "a.wav", tmp_path / "b.wav", 1)


def test_frozen_item_edit_prompt_index_matches_generator():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "benchmarks/reaper-item-edits-v1.json").read_text(encoding="utf-8"))
    expected = []
    for chain in generate_item_edit_chains(manifest["chains"], manifest["seed"]):
        for step in chain.steps:
            payload = json.dumps(step.task.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            expected.append({"id": step.task.id, "chain_id": chain.id, "split": chain.split,
                "stage": step.task.tags[1], "prompt": step.task.prompt,
                "task_sha256": hashlib.sha256(payload).hexdigest()})
    assert manifest["samples"] == expected
