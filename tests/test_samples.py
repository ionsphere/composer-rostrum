from copy import deepcopy

from composer_rostrum.environment import MusicEnvironment, ToolError
from composer_rostrum.sample_tasks import sample_project, sample_tasks


def test_sample_clip_transformations_are_logged():
    env = MusicEnvironment(sample_project(), ["inspect_project", "trim_clip", "set_clip_pitch", "stretch_clip", "reverse_clip"])
    env.call("inspect_project")
    env.call("trim_clip", track_id="samples", clip_id="hit-1", source_start=0.4, source_end=0.9)
    env.call("set_clip_pitch", track_id="samples", clip_id="hit-1", semitones=-12)
    env.call("stretch_clip", track_id="samples", clip_id="hit-1", ratio=1.5)
    env.call("reverse_clip", track_id="samples", clip_id="hit-1", reversed=True)

    clip = env.project.tracks[0]["clips"][0]
    assert clip["source_start"] == 0.4
    assert clip["source_end"] == 0.9
    assert clip["pitch_semitones"] == -12.0
    assert clip["stretch_ratio"] == 1.5
    assert clip["reversed"] is True
    assert [event.tool for event in env.trajectory] == ["inspect_project", "trim_clip", "set_clip_pitch", "stretch_clip", "reverse_clip"]
    assert any(path.endswith("source_start") for path in env.trajectory[1].changed_paths)


def test_sampler_mapping_references_provenanced_asset():
    env = MusicEnvironment(sample_project(), ["create_sampler", "map_sample_slice"])
    env.call("create_sampler", track_id="sampler", sampler_id="found-kit", name="Found Kit")
    env.call("map_sample_slice", track_id="sampler", sampler_id="found-kit", asset_id="field-hit", note=36, source_start=0.4, source_end=0.9)
    mapping = env.project.tracks[1]["instruments"][0]["mappings"][0]
    assert mapping["asset_id"] == "field-hit"
    assert env.project.assets[0]["provenance"]["rights_verified"] is True


def test_derived_asset_preserves_lineage():
    env = MusicEnvironment(sample_project(), ["register_derived_asset"])
    env.call(
        "register_derived_asset",
        asset_id="bass-hit",
        name="Bass hit",
        duration_seconds=0.5,
        derived_from=["field-hit"],
        operations=[{"op": "trim", "start": 0.4, "end": 0.9}, {"op": "pitch", "semitones": -17}],
    )
    derived = env.project.assets[-1]
    assert derived["provenance"]["derived_from"] == ["field-hit"]
    assert derived["provenance"]["operations"][1]["semitones"] == -17


def test_sample_task_catalog_has_distinct_workflow_families():
    tasks = sample_tasks()
    assert len(tasks) == 5
    assert len({task.id for task in tasks}) == 5
    assert {tag for task in tasks for tag in task.tags} >= {"samples", "creator-workflow", "deterministic"}


def test_unlisted_sample_tool_is_blocked():
    env = MusicEnvironment(deepcopy(sample_project()), ["inspect_project"])
    try:
        env.call("set_clip_pitch", track_id="samples", clip_id="hit-1", semitones=-12)
    except ToolError:
        pass
    else:
        raise AssertionError("environment allowed a tool not granted by the task")
