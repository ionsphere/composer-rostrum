import pytest
import json
import importlib.util
from pathlib import Path
import hashlib

from composer_rostrum import music_programs as programs
from composer_rostrum.local_action_agent import LocalActionAgent


def test_discovery_separates_installation_from_control_connection(monkeypatch):
    monkeypatch.setattr(programs, "_executable", lambda key, command, paths: f"/{command}" )
    monkeypatch.setattr(programs, "_audacity_connected", lambda: False)
    discovered = programs.discover_music_programs()
    assert [(p.name, p.installed, p.usable) for p in discovered] == [
        ("reaper", True, True), ("audacity", True, False)]
    assert "unavailable" in discovered[1].reason


def test_discovery_marks_live_audacity_pipe_usable(monkeypatch):
    monkeypatch.setattr(programs, "_executable", lambda key, command, paths: f"/{command}")
    monkeypatch.setattr(programs, "_audacity_connected", lambda: True)
    audacity = programs.discover_music_programs()[1]
    assert audacity.usable
    assert {"mute_track", "split_audio_clip", "normalize_audio", "render"}.issubset(audacity.operations)


def test_route_requires_real_capability_and_reports_no_tool():
    reaper = programs.MusicProgram("reaper", "reaper", True, True,
                                   ("mute_track", "set_tempo"), "bridge")
    audacity = programs.MusicProgram("audacity", "audacity", True, False,
                                     ("mute_track",), "script", "bridge not verified")
    assert programs.choose_music_program(["mute_track"], [reaper, audacity]).program == "reaper"
    assert programs.choose_music_program(["mute_track"], [reaper, audacity], "audacity").status == "unavailable"
    assert programs.choose_music_program(["render"], [reaper, audacity]).to_dict() == {
        "status": "unavailable", "program": None,
        "reason": "No connected music program supports render.",
        "required_operations": ("render",)}
    connected = programs.MusicProgram("audacity", "audacity", True, True,
                                      ("mute_track",), "script")
    assert programs.choose_music_program(["mute_track"], [reaper, connected]).program == "audacity"
    assert programs.choose_music_program(["set_tempo"], [connected]).status == "unavailable"
    assert programs.choose_music_program([], [reaper]).status == "unavailable"


def test_same_intent_translates_to_two_program_languages():
    assert programs.translate_mute_track("reaper", "drums", True) == [
        {"tool": "mute_track", "arguments": {"track_id": "drums", "muted": True}}]
    assert programs.translate_mute_track("audacity", "drums", True, audacity_track_index=2) == [
        "SelectTracks: Track=2 TrackCount=1 Mode=Set", "SetTrackAudio: Mute=1"]
    with pytest.raises(ValueError, match="verified"):
        programs.translate_mute_track("audacity", "drums", False)


def test_routing_training_keeps_phrases_and_no_tool_cases_split(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts/export_program_routing.py"
    spec = importlib.util.spec_from_file_location("export_program_routing", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = tmp_path / "original"
    original.mkdir()
    for split in ("train", "dev"):
        (original / f"{split}.jsonl").write_text('{"id":"old"}\n', encoding="utf-8")
    (original / "manifest.json").write_text(json.dumps({
        "format": "source-v1", "test_split_exported": False,
        "files": {split: hashlib.sha256((original / f"{split}.jsonl").read_bytes()).hexdigest()
                  for split in ("train", "dev")}}), encoding="utf-8")
    output = tmp_path / "output"
    manifest = module.export(original, output)
    train = list(module.routing_rows("train"))
    dev = list(module.routing_rows("dev"))
    assert {row["chain_id"] for row in train}.isdisjoint({row["chain_id"] for row in dev})
    assert any(json.loads(row["completion"])["tool"] == "report_unavailable" for row in dev)
    assert any(json.loads(row["completion"])["arguments"].get("program") == "audacity"
               for row in dev)
    assert manifest["counts"]["train"]["routing_written"] == 16 * len(train)
    assert manifest["test_split_exported"] is False


def test_agent_rejects_hallucinated_and_disconnected_programs():
    agent = object.__new__(LocalActionAgent)
    catalog = [programs.MusicProgram("reaper", "reaper", True, True,
                                     ("mute_track",), "bridge"),
               programs.MusicProgram("audacity", "audacity", True, False,
                                     ("mute_track",), "script")]
    agent._generate = lambda system, prompt: '{"tool":"select_music_program","arguments":{"program":"audacity"}}'
    assert agent.choose_program("Mute drums", ["mute_track"], catalog).status == "unavailable"
    agent._generate = lambda system, prompt: '{"tool":"select_music_program","arguments":{"program":"reaper"}}'
    assert agent.choose_program("Mute drums", ["mute_track"], catalog).program == "reaper"
    agent._generate = lambda system, prompt: pytest.fail("model must not run with no viable program")
    assert agent.choose_program("Render mix", ["render"], catalog).status == "unavailable"
