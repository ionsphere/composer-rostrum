"""Freeze checked native rhythm/arrangement samples and control outcomes."""
from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path

from composer_rostrum.corpus_capture import sha256, write_json
from composer_rostrum.evaluator import evaluate
from composer_rostrum.rhythm_arrangement_corpus import (CORPUS_VERSION,
    generate_rhythm_arrangement_chains)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--controls", type=Path)
    args = parser.parse_args()
    root = args.capture.resolve()
    dataset = root / "dataset"
    report = json.loads((dataset / "validation.json").read_text(encoding="utf-8"))
    assert report["corpus"] == CORPUS_VERSION
    chains = generate_rhythm_arrangement_chains(report["chains"], report["seed"])
    assert report["passed"] == report["samples"] == 2 * len(chains)
    assert report["relocated_restart_checks"] == len(chains)
    assert all(row["passed"] and row["native_ids_preserved"] and row["negative_controls_rejected"]
               for row in report["evidence"])
    assert all(row["relocated_restart"]["readback"] and row["relocated_restart"]["native_ids"] and
               row["relocated_restart"]["pcm_equivalent_24bit"]
               for row in report["evidence"] if "relocated_restart" in row)
    manifest = {"corpus": CORPUS_VERSION, "seed": report["seed"], "chains": len(chains), "samples": []}
    for chain in chains:
        for step in chain.steps:
            task = step.task
            public = json.loads((dataset / "inputs" / f"{task.id}.json").read_text(encoding="utf-8"))
            private = json.loads((dataset / "private" / f"{task.id}.json").read_text(encoding="utf-8"))
            assert private["task"] == task.to_dict()
            assert private["native_ids_preserved"] and all(private["negative_controls"].values())
            assert all(row.passed for row in evaluate(task, task.initial_project, step.expected))
            source = dataset / public["input_state"] / "render.wav"
            target = dataset / private["target_state"] / "render.wav"
            assert source.is_file() and target.is_file()
            assert sha256(source) != sha256(target)
            payload = json.dumps(task.to_dict(), sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False).encode("utf-8")
            manifest["samples"].append({"id": task.id, "chain_id": chain.id,
                "split": chain.split, "stage": task.tags[1], "prompt": task.prompt,
                "task_sha256": hashlib.sha256(payload).hexdigest()})
    archive = root / f"{CORPUS_VERSION}.zip"
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
        "archive_sha256": sha256(archive), "archive_bytes": archive.stat().st_size,
        "archive_file_checksums_verified": len(checksums),
        "reference_kind": "procedural-control", "model_runs": "not_run",
        "artifact_directory": root.as_posix()}
    if args.controls:
        controls = json.loads(args.controls.read_text(encoding="utf-8"))
        assert len(controls) == 6 and all(row["ok"] for row in controls)
        compact["exported_input_controls"] = controls
    write_json(Path("docs/validation") / f"{CORPUS_VERSION}.json", compact)
    print(json.dumps({k: v for k, v in compact.items() if k != "exported_input_controls"}, indent=2))


if __name__ == "__main__":
    main()
