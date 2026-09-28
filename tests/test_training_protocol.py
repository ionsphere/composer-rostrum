import json

import pytest

from composer_rostrum.training_protocol import SchemaEnvironment, action, observation, parse_action, prompt
from composer_rostrum.model_agent import tool_schemas
from composer_rostrum.corpus import generate_chains


def test_action_protocol_keeps_tool_history_and_rejects_unavailable_tools():
    history = [{"action": action("inspect_project", {}),
                "observation": {"tracks": [{"id": "samples"}]}}]
    text = prompt("Adjust the item gain", [{"name": "set_clip_gain"}], history)
    assert "Adjust the item gain" in text
    assert '"tracks":[{"id":"samples"}]' in text
    assert parse_action('{"tool":"set_clip_gain","arguments":{"gain_db":-6}}',
                        {"set_clip_gain"})["arguments"]["gain_db"] == -6
    with pytest.raises(ValueError, match="unknown tool"):
        parse_action('{"tool":"set_track_gain","arguments":{}}', {"set_clip_gain"})
    with pytest.raises(ValueError, match="finish"):
        parse_action('{"tool":"finish","arguments":{"gain_db":0}}', set())


def test_render_observation_excludes_paths_and_private_metadata():
    raw = {"render_id": "r0002", "path": "C:/worker/private.wav",
           "metadata": {"native_project_hash": "secret"},
           "metrics": {"rms_dbfs": -12.0, "silent": False, "content_hash": "secret"}}
    compacted = observation("render", raw)
    assert compacted == {"render_id": "r0002", "metrics": {"rms_dbfs": -12.0, "silent": False}}
    assert "secret" not in json.dumps(compacted)


def test_export_schemas_cover_every_native_tool():
    task = generate_chains(1)[0].steps[0].task
    environment = SchemaEnvironment(task.initial_project, task.allowed_tools)
    assert {schema["name"] for schema in tool_schemas(environment)} == set(task.allowed_tools)
