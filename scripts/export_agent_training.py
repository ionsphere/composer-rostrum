"""Export checksum-verified reference tool traces without crossing chain splits."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from composer_rostrum.corpus_capture import sha256, write_json
from composer_rostrum.model_agent import tool_schemas
from composer_rostrum.environment import MusicEnvironment
from composer_rostrum.models import RostrumTask
from composer_rostrum.training_protocol import SYSTEM, action, compact, observation, prompt


class SchemaEnvironment(MusicEnvironment):
    """Expose native render tool signatures without opening a REAPER session."""

    def _tool_render(self, **arguments):
        raise NotImplementedError

    def _tool_inspect_render(self, render_id: str):
        raise NotImplementedError

    def _tool_analyze_render(self, render_id: str):
        raise NotImplementedError


def export(datasets: list[Path], output: Path):
    output.mkdir(parents=True, exist_ok=False)
    counts = Counter()
    manifests = []
    chain_splits = {}
    files = {split: (output / f"{split}.jsonl").open("w", encoding="utf-8", newline="\n")
             for split in ("train", "dev")}
    try:
        for root in datasets:
            root = root.resolve()
            inventory_path = root / "checksums.json"
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            def checked(relative: str) -> Path:
                path = (root / relative).resolve()
                if not path.is_relative_to(root) or inventory.get(relative) != sha256(path):
                    raise ValueError(f"dataset checksum mismatch: {root.name}/{relative}")
                return path
            index = checked("samples.jsonl")
            validation = json.loads(checked("validation.json").read_text(encoding="utf-8"))
            manifests.append({"corpus": validation["corpus"], "index_sha256": sha256(index),
                              "samples": validation["samples"]})
            for line in index.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                public = json.loads(checked(row["input"]).read_text(encoding="utf-8"))
                split = public["split"]
                chain_key = (validation["corpus"], row["chain_id"])
                if chain_key in chain_splits and chain_splits[chain_key] != split:
                    raise ValueError("one chain crosses dataset splits")
                chain_splits[chain_key] = split
                if split == "test":
                    continue
                private = json.loads(checked(row["private_target"]).read_text(encoding="utf-8"))
                task = RostrumTask.from_dict(private["task"])
                if (task.id != public["id"] or task.prompt != public["prompt"] or
                        task.allowed_tools != public["allowed_tools"]):
                    raise ValueError("public/private task disagreement")
                schemas = tool_schemas(SchemaEnvironment(task.initial_project, task.allowed_tools))
                if {schema["name"] for schema in schemas} != set(task.allowed_tools):
                    raise ValueError(f"missing native tool schema: {task.id}")
                history = []
                trajectory = private["trajectory"]
                if not trajectory or any(event["error"] for event in trajectory):
                    raise ValueError(f"reference trace has errors: {task.id}")
                for turn, event in enumerate([*trajectory, {"tool": "finish", "arguments": {}}]):
                    target = action(event["tool"], event["arguments"])
                    example = {"id": f"{task.id}:{turn}", "sample_id": task.id,
                               "corpus": validation["corpus"], "chain_id": row["chain_id"],
                               "split": split, "system": SYSTEM,
                               "prompt": prompt(task.prompt, schemas, history),
                               "completion": compact(target)}
                    files[split].write(compact(example) + "\n")
                    counts[(split, validation["corpus"])] += 1
                    if event["tool"] != "finish":
                        history.append({"action": target,
                                        "observation": observation(event["tool"], event["result"])})
    finally:
        for handle in files.values():
            handle.close()
    report = {"format": "rostrum-next-action-v2", "datasets": manifests,
              "examples": {split: sum(count for (part, _), count in counts.items() if part == split)
                           for split in ("train", "dev")},
              "by_corpus": {f"{split}/{corpus}": count for (split, corpus), count in counts.items()},
              "files": {split: hashlib.sha256((output / f"{split}.jsonl").read_bytes()).hexdigest()
                        for split in ("train", "dev")},
              "test_split_exported": False}
    write_json(output / "manifest.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("datasets", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.datasets, args.output), indent=2))


if __name__ == "__main__":
    main()
