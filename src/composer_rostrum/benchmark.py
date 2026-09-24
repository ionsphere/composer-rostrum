"""Versioned Rostrum-120 splits, private reference oracles and comparable reports."""
from __future__ import annotations
import argparse
import hashlib
import json
import random
from collections import Counter
from copy import deepcopy
from pathlib import Path

from .agent import ReferenceAgent
from .environment import MusicEnvironment, _diff_paths
from .generator import generate_task
from .symbolic_generator import generate_symbolic_task
from .multistep_generator import generate_multistep_task
from .models import RostrumTask
from .runner import run_task

VERSION = "rostrum-120-v1"


class NoOpAgent:
    def solve(self, task, environment):
        environment.call("inspect_project")


class DamagingAgent:
    """Negative evaluator control; intentionally violates the environment boundary."""
    def solve(self, task, environment):
        ReferenceAgent().solve(task, environment)
        environment._project.metadata["negative_control_damage"] = True


def oracle(task: RostrumTask) -> dict:
    env = MusicEnvironment(task.initial_project, task.allowed_tools)
    public = deepcopy(task)
    public.evaluators = []
    ReferenceAgent().solve(public, env)
    return {"expected_project": env.project.to_dict(), "trajectory": [e.to_dict() for e in env.trajectory],
            "changed_paths": _diff_paths(task.initial_project.to_dict(), env.project.to_dict())}


def fingerprint(task: RostrumTask) -> str:
    project = task.initial_project.to_dict()
    project.pop("metadata", None)
    return hashlib.sha256(json.dumps({"project": project, "prompt": task.prompt}, sort_keys=True).encode()).hexdigest()


def generate_benchmark(seed: int = 20260922) -> dict[str, list[RostrumTask]]:
    rng = random.Random(seed)
    splits = {"train": [], "dev": [], "test": []}
    seen = set()
    for generator, families in ((generate_task, 5), (generate_symbolic_task, 4), (generate_multistep_task, 3)):
        for family in range(families):
            for variant in range(10):
                for attempt in range(10000):
                    task = generator(family, rng.randrange(2**31))
                    digest = fingerprint(task)
                    if digest not in seen:
                        break
                else:
                    raise ValueError("could not produce unique benchmark task")
                seen.add(digest)
                split = "train" if variant < 6 else "dev" if variant < 8 else "test"
                task.id = f"{task.id}-{variant:02d}"
                truth = oracle(task)
                if not truth["changed_paths"]:
                    raise ValueError(f"vacuous reference solution: {task.id}")
                task.evaluators.append({"type": "preserve_except", "paths": truth["changed_paths"]})
                splits[split].append(task)
    return splits


def write_benchmark(directory: Path, seed: int = 20260922) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"version": VERSION, "seed": seed, "tasks": []}
    (directory / "oracles").mkdir()
    for split, tasks in generate_benchmark(seed).items():
        (directory / split).mkdir()
        for task in tasks:
            path = directory / split / f"{task.id}.json"
            content = json.dumps(task.to_dict(), indent=2) + "\n"
            path.write_text(content, encoding="utf-8", newline="\n")
            (directory / "oracles" / f"{task.id}.json").write_text(json.dumps(oracle(task), indent=2), encoding="utf-8")
            manifest["tasks"].append({"id": task.id, "split": split, "family": task.initial_project.metadata["family"],
                "path": path.relative_to(directory).as_posix(), "sha256": hashlib.sha256(content.encode()).hexdigest(),
                "fingerprint": fingerprint(task)})
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def summarize(outcomes: list[dict]) -> dict:
    def stats(rows):
        eligible = [r for r in rows if r["infrastructure"]["ok"]]
        return {"tasks": len(rows), "passed": sum(r["passed"] for r in eligible),
                "infrastructure_failures": len(rows)-len(eligible),
                "pass_rate": sum(r["passed"] for r in eligible)/len(eligible) if eligible else None,
                "failure_classes": dict(Counter(r.get("failure_class", "passed") for r in rows))}
    report = stats(outcomes)
    report["tool_calls"] = sum(r.get("tool_calls", 0) for r in outcomes)
    report["renders"] = sum(len(r.get("renders", [])) for r in outcomes)
    report["elapsed_seconds"] = sum(r.get("elapsed_seconds", 0) for r in outcomes)
    report["model_usage"] = {k: sum(r.get("model_usage", {}).get(k, 0) for r in outcomes)
                             for k in ("input_tokens", "output_tokens", "total_tokens")}
    for field in ("level", "family", "execution_level"):
        report["by_"+field] = {str(key): stats([r for r in outcomes if r.get(field) == key])
                              for key in sorted({r.get(field) for r in outcomes}, key=str)}
    return report


def main():
    parser = argparse.ArgumentParser(description="Generate and validate Rostrum-120")
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=20260922)
    parser.add_argument("--controls", action="store_true", help="Run reference/no-op/damaging controls (not model comparisons)")
    args = parser.parse_args()
    manifest = write_benchmark(args.output, args.seed)
    if args.controls:
        reports = {}
        for name, agent in (("reference", ReferenceAgent()), ("no-op", NoOpAgent()), ("damaging", DamagingAgent())):
            outcomes = [run_task(RostrumTask.from_dict(json.loads((args.output / row["path"]).read_text(encoding="utf-8"))), agent)
                        for row in manifest["tasks"]]
            reports[name] = summarize(outcomes)
            (args.output / f"{name}-outcomes.json").write_text(json.dumps(outcomes, indent=2), encoding="utf-8")
        (args.output / "controls.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
        print(json.dumps(reports, indent=2))
        if reports["reference"]["passed"] != len(manifest["tasks"]) or any(
                reports[name]["passed"] or reports[name]["infrastructure_failures"] for name in ("no-op", "damaging")):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
