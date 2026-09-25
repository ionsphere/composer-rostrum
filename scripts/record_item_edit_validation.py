"""Freeze the native item-edit corpus index only after full audio/state verification."""
from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path

from composer_rostrum.corpus_capture import fixture_pcm_matches, moved_item_pcm_matches, pcm_equivalent, sha256, write_json
from composer_rostrum.item_edit_corpus import CORPUS_VERSION, generate_item_edit_chains


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--controls", type=Path)
    args = parser.parse_args()
    capture = args.capture.resolve()
    dataset = capture / "dataset"
    report = json.loads((dataset / "validation.json").read_text(encoding="utf-8"))
    assert report["corpus"] == CORPUS_VERSION
    chains = generate_item_edit_chains(report["chains"], report["seed"])
    assert report["passed"] == report["samples"] == 2 * len(chains)
    assert report["relocated_restart_checks"] == len(chains)
    assert all(e["passed"] and e["native_ids_preserved"] and e["negative_controls_rejected"]
               for e in report["evidence"])
    assert all(e["relocated_restart"]["readback"] and e["relocated_restart"]["native_ids"] and
               e["relocated_restart"]["pcm_equivalent_24bit"]
               for e in report["evidence"] if "relocated_restart" in e)
    manifest = {"corpus": CORPUS_VERSION, "seed": report["seed"], "chains": len(chains), "samples": []}
    for chain in chains:
        for step in chain.steps:
            task = step.task
            public = json.loads((dataset / "inputs" / f"{task.id}.json").read_text(encoding="utf-8"))
            private = json.loads((dataset / "private" / f"{task.id}.json").read_text(encoding="utf-8"))
            assert private["task"] == task.to_dict()
            assert private["native_ids_preserved"] and all(private["negative_controls"].values())
            source = dataset / public["input_state"] / "render.wav"
            target = dataset / private["target_state"] / "render.wav"
            assert source.is_file() and target.is_file()
            if task.tags[1] == "split":
                assert pcm_equivalent(source, target, 1), task.id
            else:
                initial_public = json.loads((dataset / "inputs" / f"{chain.steps[0].task.id}.json").read_text(encoding="utf-8"))
                original = dataset / initial_public["input_state"] / "render.wav"
                original_asset = dataset / initial_public["input_state"] / "assets/tone.wav"
                start_project = chain.steps[0].task.initial_project
                start = start_project.tracks[0]["clips"][0]["timeline_start_beats"]
                cut = step.expected.tracks[0]["clips"][0]["source_end"]
                destination = step.expected.tracks[0]["clips"][1]["timeline_start_beats"]
                assert fixture_pcm_matches(original_asset, original, start_project.tempo, start), task.id
                assert moved_item_pcm_matches(original, target, start_project.tempo, start, cut, destination), task.id
            payload = json.dumps(task.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            manifest["samples"].append({"id": task.id, "chain_id": chain.id, "split": chain.split,
                "stage": task.tags[1], "prompt": task.prompt, "task_sha256": hashlib.sha256(payload).hexdigest()})
    archive = capture / f"{CORPUS_VERSION}.zip"
    assert archive.is_file()
    checksums = json.loads((dataset / "checksums.json").read_text(encoding="utf-8"))
    assert all(sha256(dataset / name) == digest for name, digest in checksums.items())
    write_json(Path("benchmarks") / f"{CORPUS_VERSION}.json", manifest)
    compact = {"corpus": CORPUS_VERSION, "seed": report["seed"], "chains": len(chains),
        "samples": len(manifest["samples"]), "splits": report["splits"],
        "stages": dict(Counter(row["stage"] for row in manifest["samples"])),
        "native_states": 3 * len(chains), "rendered_states": 3 * len(chains),
        "semantic_and_render_checks_passed": report["passed"],
        "negative_controls_rejected": report["passed"],
        "relocated_restart_checks": report["relocated_restart_checks"],
        "split_pcm_preservation_checks": len(chains),
        "move_pcm_change_checks": len(chains),
        "archive_sha256": sha256(archive), "archive_bytes": archive.stat().st_size,
        "archive_file_checksums_verified": len(checksums),
        "reference_kind": "procedural-control", "model_runs": "not_run",
        "artifact_directory": capture.as_posix()}
    if args.controls:
        controls = json.loads(args.controls.read_text(encoding="utf-8"))
        assert len(controls) == 4 and all(item["ok"] for item in controls)
        compact["exported_input_controls"] = controls
    write_json(Path("docs/validation") / f"{CORPUS_VERSION}.json", compact)
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
