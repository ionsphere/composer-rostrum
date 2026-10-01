import io
import json
from pathlib import Path

import pytest

from composer_rostrum.backends.audacity.corpus import CASES, apply_action
from composer_rostrum.backends.audacity.eval import score
from composer_rostrum.backends.audacity.pipe import AudacityPipe, AudacityPipeError


class RecordingPipe:
    def __init__(self):
        self.commands = []

    def command(self, value):
        self.commands.append(value)
        return "BatchCommand finished: OK\n\n"


def test_pipe_protocol_writes_one_command_and_parses_json():
    writer = io.StringIO()
    reader = io.StringIO('[{"name":"guitar","mute":0}]\nBatchCommand finished: OK\n\n')
    pipe = AudacityPipe(writer, reader, "\r\n\0")
    assert pipe.json_info("Tracks") == [{"name": "guitar", "mute": 0}]
    assert writer.getvalue() == "GetInfo: Type=Tracks Format=JSON\r\n\0"


def test_pipe_rejects_multiline_and_failed_commands():
    with pytest.raises(ValueError, match="one Audacity command"):
        AudacityPipe(io.StringIO(), io.StringIO(), "\n").command("New:\nClose:")
    pipe = AudacityPipe(io.StringIO(), io.StringIO("BatchCommand finished: Failed\n\n"), "\n")
    with pytest.raises(AudacityPipeError, match="failed"):
        pipe.command("Bad:")


def test_reference_actions_use_verified_audacity_units():
    pipe = RecordingPipe()
    assert apply_action(pipe, {"op": "volume", "track": 0, "db": -6})[-1] == \
        "SetTrackAudio: Volume=-6.0"
    assert apply_action(pipe, {"op": "pan", "track": 1, "percent": -50})[-1] == \
        "SetTrackAudio: Pan=-50.0"
    assert apply_action(pipe, {"op": "split", "track": 0, "at": 0.75})[-1] == "Split:"
    assert pipe.commands == [
        "SelectTracks: Track=0 TrackCount=1 Mode=Set", "SetTrackAudio: Volume=-6.0",
        "SelectTracks: Track=1 TrackCount=1 Mode=Set", "SetTrackAudio: Pan=-50.0",
        "SelectTracks: Track=0 TrackCount=1 Mode=Set",
        "Select: Start=0.75 End=0.75 Track=0 TrackCount=1 Mode=Set", "Split:"]


def test_cases_cover_creation_style_edits_and_iterative_revision():
    assert len(CASES) == 12
    assert len({case["id"] for case in CASES}) == len(CASES)
    assert {action["op"] for case in CASES for action in case["actions"]} >= {
        "mute", "solo", "volume", "pan", "rename", "split", "fade_in", "fade_out", "normalize"}
    assert any(case.get("before") for case in CASES)
    assert any(len(case["actions"]) > 1 for case in CASES)


def test_private_score_requires_state_clips_and_pcm():
    audio = {"pcm_hash": "abc", "frames": 4, "sample_rate": 48000, "channels": 2,
             "sample_width": 2, "rms_dbfs": -12.0}
    state = {"tracks": [{"name": "guitar", "kind": "wave", "start": 0, "end": 2,
                          "pan": 0.0, "volume": 1.0, "channels": 1, "solo": 0, "mute": 1}],
             "clips": [{"track": 0, "start": 0, "end": 2, "name": "guitar"}], "audio": audio}
    assert score(state, state)["passed"]
    changed = {**state, "tracks": [{**state["tracks"][0], "mute": 0}]}
    assert not score(state, changed)["passed"]
    changed = {**state, "audio": {**audio, "pcm_hash": "different"}}
    assert not score(state, changed)["passed"]


def test_audacity_feature_ledger_is_complete_and_honest():
    path = Path(__file__).resolve().parents[1] / "benchmarks/audacity-feature-coverage-v1.json"
    ledger = json.loads(path.read_text(encoding="utf-8"))
    features = ledger["features"]
    assert len(features) >= 50
    assert len({feature["id"] for feature in features}) == len(features)
    assert {feature["status"] for feature in features} == {"native_verified", "partial", "open", "external"}
    assert all("evidence" in feature for feature in features if feature["status"] == "native_verified")
    reopen = next(feature for feature in features if feature["id"] == "project.open.reopen")
    assert reopen["status"] == "partial"
