"""Score Audacity edits from independent project readback and rendered audio."""
from __future__ import annotations

import json
from pathlib import Path

from ...audio import analyze_wav


TRACK_FIELDS = ("name", "kind", "start", "end", "pan", "volume", "channels", "solo", "mute")
CLIP_FIELDS = ("track", "start", "end", "name")


def _canonical(rows: list[dict], fields: tuple[str, ...]) -> list[dict]:
    return [{key: row.get(key) for key in fields} for row in rows]


def score(target: dict, observed: dict) -> dict:
    """Private target remains separate from the agent's prompt/input files."""
    expected_tracks = _canonical(target["tracks"], TRACK_FIELDS)
    actual_tracks = _canonical(observed["tracks"], TRACK_FIELDS)
    track_matches = []
    for expected, actual in zip(expected_tracks, actual_tracks):
        track_matches.append({key: abs(expected[key] - actual[key]) <= 1e-5
                              if isinstance(expected[key], float) and isinstance(actual[key], (float, int))
                              else expected[key] == actual[key] for key in TRACK_FIELDS})
    tracks_ok = len(expected_tracks) == len(actual_tracks) and all(all(row.values()) for row in track_matches)
    expected_clips = _canonical(target["clips"], CLIP_FIELDS)
    actual_clips = _canonical(observed["clips"], CLIP_FIELDS)
    clips_ok = expected_clips == actual_clips
    expected_audio, actual_audio = target["audio"], observed["audio"]
    audio_ok = (expected_audio["pcm_hash"] == actual_audio["pcm_hash"] and
                all(expected_audio[key] == actual_audio[key] for key in
                    ("frames", "sample_rate", "channels", "sample_width")))
    return {"passed": tracks_ok and clips_ok and audio_ok, "tracks_ok": tracks_ok,
            "clips_ok": clips_ok, "audio_ok": audio_ok, "track_fields": track_matches,
            "expected_clips": expected_clips, "observed_clips": actual_clips,
            "expected_rms_dbfs": expected_audio["rms_dbfs"],
            "observed_rms_dbfs": actual_audio["rms_dbfs"]}


def evaluate_case(case_dir: Path, tracks: list[dict], clips: list[dict], wav: Path) -> dict:
    private = json.loads((case_dir / "private.json").read_text(encoding="utf-8"))
    observed = {"tracks": tracks, "clips": clips, "audio": analyze_wav(wav)}
    return score(private["target"], observed)
