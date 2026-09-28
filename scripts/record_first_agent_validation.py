"""Freeze compact evidence for the first local REAPER tool-agent checkpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from composer_rostrum.corpus_capture import write_json


CASES = [
    ("gain-initial", "gain-0006-00-quiet", "native-base-gain", "native-adapted-gain"),
    ("gain-revision", "gain-0006-01-loud", "native-base-gain-revision", "native-adapted-gain-revision"),
    ("item-split", "item-0006-00-split", "native-base-split", "native-adapted-split"),
    ("kick-rhythm", "rhythm-0006-00-kick-rhythm", None, "native-adapted-rhythm"),
    ("instrument-add", "instrument-0006-00-add-a", None, "native-adapted-instrument"),
]


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / "data-final/manifest.json").read_text(encoding="utf-8"))
    run = json.loads((root / "run-002/report.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "rostrum-next-action-v2"
    for split in ("train", "dev"):
        assert manifest["files"][split] == sha256(root / "data-final" / f"{split}.jsonl")
        assert run[f"{split}_sha256"] == manifest["files"][split]
    assert manifest["test_split_exported"] is False
    assert run["adapted"]["action_exact"] > run["baseline"]["action_exact"]
    assert run["adapted"]["tool_correct"] > run["baseline"]["tool_correct"]
    native = []
    for name, sample_id, base_folder, adapted_folder in CASES:
        row = {"case": name, "sample_id": sample_id}
        for label, folder in (("base", base_folder), ("adapted", adapted_folder)):
            if folder is None:
                continue
            path = root / folder
            result = json.loads((path / "outcome.json").read_text(encoding="utf-8"))
            public = json.loads((path / "input.json").read_text(encoding="utf-8"))
            decisions = json.loads((path / "model-decisions.json").read_text(encoding="utf-8"))
            assert result["task_id"] == sample_id == public["id"] and public["split"] == "dev"
            assert result["infrastructure"]["ok"]
            row[label] = {"passed": result["passed"], "failure_class": result.get("failure_class"),
                          "decisions": len(decisions),
                          "outcome_sha256": sha256(path / "outcome.json")}
        native.append(row)
    paired = [row for row in native if "base" in row]
    assert len(paired) == 3
    assert all(not row["base"]["passed"] and row["adapted"]["passed"] for row in paired)
    adapter = root / "run-002/adapter/adapter_model.safetensors"
    report = {"experiment": "first-local-music-agent-v1", "base_model": run["base_model"],
              "base_revision": "7ae557604adf67be50417f59c2c2f167def9a775",
              "adapter_kind": run["adapter"], "adapter_sha256": sha256(adapter),
              "adapter_bytes": adapter.stat().st_size,
              "data_format": manifest["format"], "source_corpora": manifest["datasets"],
              "exported_actions": manifest["examples"], "train_sha256": run["train_sha256"],
              "dev_sha256": run["dev_sha256"], "test_split_exported": False,
              "max_length": run["max_length"], "max_steps": run["max_steps"],
              "generation_tokens": run["generation_tokens"],
              "usable_train_actions": run["train_examples"],
              "overlength_train_actions": run["skipped_overlength"],
              "teacher_forced_dev": {"sampled": run["adapted"]["n"],
                  "base": {k: run["baseline"][k] for k in ("parsed", "tool_correct", "action_exact")},
                  "adapted": {k: run["adapted"][k] for k in ("parsed", "tool_correct", "action_exact")}},
              "native_dev_cases": native,
              "paired_native_passes": {"base": sum(row["base"]["passed"] for row in paired),
                                       "adapted": sum(row["adapted"]["passed"] for row in paired),
                                       "cases": len(paired)},
              "model_status": "experimental; not a full REAPER pass-rate estimate"}
    write_json(Path("docs/validation/first-local-music-agent-v1.json"), report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
