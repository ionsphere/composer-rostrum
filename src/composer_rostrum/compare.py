"""Execute user-selected model configurations against exactly the same frozen split."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from .benchmark import summarize
from .model_agent import ResponsesAgent
from .runner import load_task, run_task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("config", type=Path, help="JSON list of named ResponsesAgent model configurations")
    parser.add_argument("output", type=Path)
    parser.add_argument("--split", choices=["train", "dev", "test"], default="test")
    args = parser.parse_args()
    configurations = json.loads(args.config.read_text(encoding="utf-8"))
    if any(c.get("model") == "REPLACE_WITH_MODEL_ID" for c in configurations):
        parser.error("replace example model IDs before running a comparison")
    names = [c["name"] for c in configurations]
    if len(names) != len(set(names)) or not names or any(not n.replace("-", "").replace("_", "").isalnum() for n in names):
        parser.error("configuration names must be unique safe directory names")
    manifest_bytes = (args.benchmark / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    rows = [row for row in manifest["tasks"] if row["split"] == args.split]
    if not rows:
        parser.error("empty benchmark split")
    tasks = []
    for row in rows:
        path = (args.benchmark / row["path"]).resolve()
        if args.benchmark.resolve() not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            parser.error("benchmark task path or content hash mismatch")
        tasks.append(load_task(path))
    # Fail missing credentials/configuration before making a partial run directory.
    agents = [(c, ResponsesAgent(**{k: v for k, v in c.items() if k != "name"})) for c in configurations]
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"benchmark": manifest["version"], "manifest_hash": hashlib.sha256(manifest_bytes).hexdigest(),
              "split": args.split, "configurations": {}, "task_ids": [t.id for t in tasks]}
    for config, agent in agents:
        outcomes = []
        for task in tasks:
            result = run_task(task, agent, workspace=args.output / config["name"] / task.id)
            outcomes.append(result)
            print(config["name"], task.id, result["passed"], flush=True)
        report["configurations"][config["name"]] = {"config": config, **summarize(outcomes)}
        (args.output / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
