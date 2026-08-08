from __future__ import annotations

from .models import MusicProject, RostrumTask


def sample_project() -> MusicProject:
    return MusicProject(
        tempo=128.0,
        meter="4/4",
        key="D_minor",
        assets=[
            {
                "id": "field-hit",
                "kind": "audio",
                "name": "Field recording hit",
                "duration_seconds": 3.2,
                "provenance": {
                    "source": "procedural_fixture",
                    "license": "benchmark-owned",
                    "rights_verified": True,
                },
            }
        ],
        tracks=[
            {
                "id": "samples",
                "name": "Samples",
                "kind": "audio",
                "clips": [
                    {
                        "id": "hit-1",
                        "asset_id": "field-hit",
                        "timeline_start_beats": 0.0,
                        "source_start": 0.0,
                        "source_end": 3.2,
                        "pitch_semitones": 0.0,
                        "stretch_ratio": 1.0,
                        "reversed": False,
                    }
                ],
            },
            {"id": "sampler", "name": "Sampler", "kind": "midi", "instruments": []},
        ],
        metadata={"generator": "sample-manipulation-v1"},
    )


def sample_tasks() -> list[RostrumTask]:
    base = sample_project()
    preserve_global = {"type": "preserve_paths", "paths": ["tempo", "meter", "key", "metadata"]}
    return [
        RostrumTask(
            "L2-SAMPLE-001-trim",
            "L2",
            "Trim clip 'hit-1' on track 'samples' to use only source audio from 0.40s through 0.90s. Change no project-level settings.",
            base,
            ["inspect_project", "trim_clip"],
            [
                {"type": "project_property", "path": "tracks.0.clips.0.source_start", "equals": 0.4},
                {"type": "project_property", "path": "tracks.0.clips.0.source_end", "equals": 0.9},
                preserve_global,
            ],
            ["samples", "trim", "creator-workflow", "deterministic"],
        ),
        RostrumTask(
            "L2-SAMPLE-002-pitch",
            "L2",
            "Pitch clip 'hit-1' on track 'samples' down 12 semitones while leaving timing and project settings intact.",
            base,
            ["inspect_project", "set_clip_pitch"],
            [
                {"type": "project_property", "path": "tracks.0.clips.0.pitch_semitones", "equals": -12.0},
                {"type": "preserve_paths", "paths": ["tempo", "meter", "key", "metadata", "tracks.0.clips.0.source_start", "tracks.0.clips.0.source_end", "tracks.0.clips.0.stretch_ratio"]},
            ],
            ["samples", "pitch", "creator-workflow", "deterministic"],
        ),
        RostrumTask(
            "L2-SAMPLE-003-stretch",
            "L2",
            "Time-stretch clip 'hit-1' on track 'samples' to 1.5x its current duration without changing its pitch.",
            base,
            ["inspect_project", "stretch_clip"],
            [
                {"type": "project_property", "path": "tracks.0.clips.0.stretch_ratio", "equals": 1.5},
                {"type": "project_property", "path": "tracks.0.clips.0.pitch_semitones", "equals": 0.0},
                preserve_global,
            ],
            ["samples", "stretch", "creator-workflow", "deterministic"],
        ),
        RostrumTask(
            "L2-SAMPLE-004-reverse",
            "L2",
            "Reverse clip 'hit-1' on track 'samples'. Do not alter its source range, pitch, or stretch ratio.",
            base,
            ["inspect_project", "reverse_clip"],
            [
                {"type": "project_property", "path": "tracks.0.clips.0.reversed", "equals": True},
                {"type": "preserve_paths", "paths": ["tracks.0.clips.0.source_start", "tracks.0.clips.0.source_end", "tracks.0.clips.0.pitch_semitones", "tracks.0.clips.0.stretch_ratio", "tempo", "meter", "key"]},
            ],
            ["samples", "reverse", "creator-workflow", "deterministic"],
        ),
        RostrumTask(
            "L2-SAMPLE-005-sampler-map",
            "L2",
            "Create sampler 'found-kit' on track 'sampler' and map source asset 'field-hit' from 0.40s to 0.90s onto MIDI note 36.",
            base,
            ["inspect_project", "create_sampler", "map_sample_slice"],
            [
                {"type": "project_property", "path": "tracks.1.instruments.0.id", "equals": "found-kit"},
                {"type": "project_property", "path": "tracks.1.instruments.0.mappings.0.note", "equals": 36},
                {"type": "project_property", "path": "tracks.1.instruments.0.mappings.0.asset_id", "equals": "field-hit"},
                preserve_global,
            ],
            ["samples", "sampler", "mapping", "creator-workflow", "deterministic"],
        ),
    ]
