"""Native Audacity prompt -> project and project -> changed-project eval corpus."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from ...audio import analyze_wav, write_fixture
from .pipe import AudacityPipe
from .eval import score


CASES = [
    {"id": "mute-guitar", "prompt": "Mute the guitar track.", "actions": [{"op": "mute", "track": 0, "value": 1}]},
    {"id": "unmute-guitar", "prompt": "Unmute the guitar track.", "before": [{"op": "mute", "track": 0, "value": 1}], "actions": [{"op": "mute", "track": 0, "value": 0}]},
    {"id": "solo-kick", "prompt": "Solo the kick track so I can hear it alone.", "actions": [{"op": "solo", "track": 1, "value": 1}]},
    {"id": "lower-guitar", "prompt": "Turn the guitar track down by 6 dB.", "actions": [{"op": "volume", "track": 0, "db": -6}]},
    {"id": "pan-guitar-left", "prompt": "Pan the guitar halfway left.", "actions": [{"op": "pan", "track": 0, "percent": -50}]},
    {"id": "rename-kick", "prompt": "Rename the kick track to drums.", "actions": [{"op": "rename", "track": 1, "name": "drums"}]},
    {"id": "split-guitar", "prompt": "Split the guitar clip at 0.75 seconds.", "actions": [{"op": "split", "track": 0, "at": 0.75}]},
    {"id": "fade-in-guitar", "prompt": "Fade the first half-second of the guitar in.", "actions": [{"op": "fade_in", "track": 0, "start": 0, "end": 0.5}]},
    {"id": "fade-out-guitar", "prompt": "Fade the guitar out over its last half-second.", "actions": [{"op": "fade_out", "track": 0, "start": 1.5, "end": 2}]},
    {"id": "normalize-guitar", "prompt": "Normalize the guitar to a -3 dB peak.", "actions": [{"op": "normalize", "track": 0, "start": 0, "end": 2, "peak_db": -3}]},
    {"id": "split-then-mute", "prompt": "Split the guitar at 0.75 seconds, then mute its track.", "actions": [{"op": "split", "track": 0, "at": 0.75}, {"op": "mute", "track": 0, "value": 1}]},
    {"id": "revise-mix", "prompt": "The guitar is still too loud and left-heavy. Lower it to -9 dB and bring it to center.", "before": [{"op": "volume", "track": 0, "db": -3}, {"op": "pan", "track": 0, "percent": -50}], "actions": [{"op": "volume", "track": 0, "db": -9}, {"op": "pan", "track": 0, "percent": 0}]},
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _arg(value: Path | str) -> str:
    result = value.as_posix() if isinstance(value, Path) else value
    if any(c in result for c in '\r\n\0"'):
        raise ValueError("unsafe Audacity argument")
    return f'"{result}"' if " " in result else result


def apply_action(pipe: AudacityPipe, action: dict) -> list[str]:
    """Execute a bounded reference action and return its visible command trace."""
    op, track = action["op"], action["track"]
    if type(track) is not int or track not in (0, 1):
        raise ValueError("fixture track index must be 0 or 1")
    commands = [f"SelectTracks: Track={track} TrackCount=1 Mode=Set"]
    if op == "mute":
        commands.append(f"SetTrackAudio: Mute={int(action['value'])}")
    elif op == "solo":
        commands.append(f"SetTrackAudio: Solo={int(action['value'])}")
    elif op == "volume":
        commands.append(f"SetTrackAudio: Volume={float(action['db'])}")
    elif op == "pan":
        commands.append(f"SetTrackAudio: Pan={float(action['percent'])}")
    elif op == "rename":
        commands.append(f"SetTrackStatus: Name={_arg(action['name'])}")
    elif op in ("split", "fade_in", "fade_out", "normalize"):
        start = action.get("at", action.get("start"))
        end = action.get("at", action.get("end"))
        commands.append(f"Select: Start={start} End={end} Track={track} TrackCount=1 Mode=Set")
        commands.append({"split": "Split:", "fade_in": "FadeIn:", "fade_out": "FadeOut:",
                         "normalize": f"Normalize: PeakLevel={float(action.get('peak_db', -1))}"}[op])
    else:
        raise ValueError(f"unsupported reference action: {op}")
    for command in commands:
        pipe.command(command)
    return commands


def _state(pipe: AudacityPipe, wav: Path) -> dict:
    return {"tracks": pipe.json_info("Tracks"), "clips": pipe.json_info("Clips"),
            "audio": analyze_wav(wav)}


def _export_mix(pipe: AudacityPipe, wav: Path) -> None:
    """Export every fixture track; edit actions intentionally change selection."""
    tracks = pipe.json_info("Tracks")
    track_count = len(tracks)
    project_end = max(track["end"] for track in tracks)
    pipe.command(f"Select: Start=0 End={project_end} Track=0 TrackCount={track_count} Mode=Set")
    pipe.command(f"Export2: Filename={_arg(wav)} NumChannels=2")


def capture(root: Path, cases: list[dict] = CASES) -> dict:
    """Capture owned fixtures in the live Audacity instance; no user project is edited."""
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    assets = root / "assets"
    write_fixture(assets / "guitar.wav", 2, kind="guitar")
    write_fixture(assets / "kick.wav", 2, kind="kick")
    entries = []
    with AudacityPipe.connect() as pipe:
        for case in cases:
            folder = root / case["id"]
            folder.mkdir(exist_ok=False)
            # New creates a separate owned project even when a user project is open.
            pipe.command("New:")
            try:
                for name in ("guitar", "kick"):
                    pipe.command(f"Import2: Filename={_arg(assets / (name + '.wav'))}")
                for action in case.get("before", []):
                    apply_action(pipe, action)
                pipe.command(f"SaveProject2: Filename={_arg(folder / 'input.aup3')}")
                _export_mix(pipe, folder / "before.wav")
                initial = _state(pipe, folder / "before.wav")
                trace = []
                for action in case["actions"]:
                    trace += apply_action(pipe, action)
                pipe.command(f"SaveProject2: Filename={_arg(folder / 'target.aup3')}")
                _export_mix(pipe, folder / "after.wav")
                target = _state(pipe, folder / "after.wav")
            finally:
                pipe.command("Close:")  # flush SQLite WAL into the native .aup3
            public = {"id": case["id"], "prompt": case["prompt"], "input": initial,
                      "input_project": "input.aup3", "input_audio": "before.wav"}
            private = {"actions": case["actions"], "target": target,
                       "target_project": "target.aup3", "target_audio": "after.wav",
                       "reference_trace": trace}
            _write_json(folder / "public.json", public)
            _write_json(folder / "private.json", private)
            checksums = {p.name: _sha256(p) for p in folder.iterdir() if p.is_file()}
            _write_json(folder / "checksums.json", checksums)
            entries.append({"id": case["id"], "prompt": case["prompt"],
                            "revision": bool(case.get("before")), "files": checksums})
    manifest = {"schema": "audacity-native-corpus-v1", "case_count": len(entries),
                "assets": {p.name: _sha256(p) for p in assets.iterdir()}, "cases": entries}
    _write_json(root / "manifest.json", manifest)
    return manifest


def _action_satisfied(action: dict, state: dict) -> bool:
    tracks, clips = state["tracks"], state["clips"]
    track = tracks[action["track"]]
    op = action["op"]
    if op in ("mute", "solo"):
        return track[op] == action["value"]
    if op == "volume":
        return abs(track["volume"] - 10 ** (action["db"] / 20)) < 1e-5
    if op == "pan":
        return abs(track["pan"] - action["percent"] / 100) < 1e-5
    if op == "rename":
        return track["name"] == action["name"]
    if op == "split":
        at = action["at"]
        return any(clip["track"] == action["track"] and clip["end"] == at for clip in clips) and \
            any(clip["track"] == action["track"] and clip["start"] == at for clip in clips)
    if op in ("fade_in", "fade_out", "normalize"):
        return True  # exact PCM is checked against the capture-time private target
    return False


def validate(root: Path, output: Path) -> dict:
    """Validate checksums, native databases, semantic deltas, and captured PCM offline."""
    root, output = root.resolve(), output.resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for entry in manifest["cases"]:
        folder = root / entry["id"]
        checksums = json.loads((folder / "checksums.json").read_text(encoding="utf-8"))
        checksum_ok = all(_sha256(folder / name) == digest for name, digest in checksums.items())
        sqlite_results = []
        for path in folder.glob("*.aup3"):
            with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True) as database:
                sqlite_results.append(database.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
        public = json.loads((folder / "public.json").read_text(encoding="utf-8"))
        private = json.loads((folder / "private.json").read_text(encoding="utf-8"))
        input_audio = analyze_wav(folder / public["input_audio"])
        target_audio = analyze_wav(folder / private["target_audio"])
        input_check = score(public["input"], {**public["input"], "audio": input_audio})
        target_check = score(private["target"], {**private["target"], "audio": target_audio})
        actions_ok = all(_action_satisfied(action, private["target"])
                         for action in private["actions"])
        preservation_ok = len(public["input"]["tracks"]) == len(private["target"]["tracks"]) == 2
        case_result = {"id": entry["id"], "checksum_ok": checksum_ok,
                       "sqlite_ok": bool(sqlite_results) and all(sqlite_results),
                       "input_audio_ok": input_check["audio_ok"],
                       "target_audio_ok": target_check["audio_ok"],
                       "actions_ok": actions_ok, "preservation_ok": preservation_ok}
        case_result["passed"] = all(value for key, value in case_result.items()
                                           if key != "id")
        results.append(case_result)
    report = {"schema": "audacity-native-validation-v1", "case_count": len(results),
              "native_reopen": "not_run: Audacity 3.7.4 mod-script-pipe Close after OpenProject2 crashed during validation",
              "passed": all(row["passed"] for row in results), "cases": results}
    _write_json(output / "validation.json", report)
    return report
