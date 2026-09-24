"""Evaluate an agent from a captured native input, with targets outside its tools."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import time

from .backends.base import BackendError
from .backends.reaper import ReaperBackend
from .corpus_capture import sha256, write_json
from .environment import project_hash
from .evaluator import evaluate
from .models import MusicProject, RostrumTask
from .render_evaluator import evaluate_renders


def dataset_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("corpus path escapes dataset")
    return path


def load_sample(dataset: Path, sample_id: str):
    """Integrity-check every consumed input/target file against the frozen inventory."""
    dataset = dataset.resolve()
    inventory = json.loads((dataset / "checksums.json").read_text(encoding="utf-8"))

    def read(relative):
        path = dataset_path(dataset, relative)
        if inventory.get(relative) != sha256(path):
            raise ValueError(f"corpus checksum mismatch: {relative}")
        return path

    rows = [json.loads(line) for line in read("samples.jsonl").read_text(encoding="utf-8").splitlines()]
    matches = [row for row in rows if row["id"] == sample_id]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one sample matching {sample_id!r}")
    row = matches[0]
    public = json.loads(read(row["input"]).read_text(encoding="utf-8"))
    private = json.loads(read(row["private_target"]).read_text(encoding="utf-8"))
    task = RostrumTask.from_dict(private["task"])
    if task.id != public["id"] or task.prompt != public["prompt"] or task.allowed_tools != public["allowed_tools"]:
        raise ValueError("public task differs from private scoring specification")
    state = public["input_state"]
    manifest = json.loads(read(state + "/state.json").read_text(encoding="utf-8"))
    for relative, digest in manifest["files"].items():
        path = read(state + "/" + relative)
        if sha256(path) != digest:
            raise ValueError("state and dataset checksums disagree")
    initial = MusicProject.from_dict(json.loads(read(state + "/project.music-ir.json").read_text(encoding="utf-8")))
    if project_hash(initial) != project_hash(task.initial_project) or project_hash(initial) != manifest["project_hash"]:
        raise ValueError("native input manifest differs from task initial state")
    return task, public, dataset_path(dataset, state)


def run_sample(dataset: Path, sample_id: str, agent, executable: str, output: Path):
    task, public, state = load_sample(dataset, sample_id)
    output.mkdir(parents=True, exist_ok=False)
    backend = ReaperBackend(executable, timeout=60)
    native = backend.materialize(task.initial_project, output)
    shutil.copyfile(state / "project.rpp", native.project_path)
    if (state / "assets").exists():
        shutil.copytree(state / "assets", output / "assets")
    # The evaluation workspace has only input material: no target states, oracle,
    # reference trace, or private task specification is staged for the worker.
    write_json(output / "input.json", public)
    session = environment = None
    result = {"task_id": task.id, "split": public["split"], "passed": False,
              "infrastructure": {"ok": True}, "results": [], "trajectory": [], "renders": []}
    started = time.monotonic()
    try:
        session = backend.open(native, resume=True)
        before = backend.readback(session)
        if project_hash(before) != project_hash(task.initial_project):
            raise BackendError("captured native input does not match declared initial state")
        environment = backend.create_environment(session, task.allowed_tools)
        public_task = deepcopy(task)
        public_task.evaluators = []
        agent.solve(public_task, environment)
        backend.commit_environment(session, environment)
        backend.save(session)
        after = backend.readback(session)
        checks = evaluate(task, before, after) + evaluate_renders(task, session.state["renders"], environment.trajectory, after)
        result.update(passed=bool(checks) and all(c.passed for c in checks), results=[asdict(c) for c in checks],
                      project=after.to_dict(), project_hash=project_hash(after))
        if not result["passed"]:
            result["failure_class"] = "evaluation"
    except BackendError as exc:
        result.update(failure_class="infrastructure", infrastructure={"ok": False, "error": str(exc)})
    except Exception as exc:
        result.update(failure_class="agent_error", error=f"{type(exc).__name__}: {exc}")
    finally:
        if environment is not None:
            result["trajectory"] = [e.to_dict() for e in environment.trajectory]
        if session is not None:
            result["renders"] = [r.to_dict() for r in session.state["renders"]]
            backend.close(session)
        if hasattr(agent, "usage"):
            result["model_usage"] = deepcopy(agent.usage)
        if hasattr(agent, "responses"):
            result["model_responses"] = deepcopy(agent.responses)
        result["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "outcome.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("sample_id")
    parser.add_argument("--reaper", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high"])
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--max-tool-calls", type=int, default=50)
    args = parser.parse_args()
    from .model_agent import ResponsesAgent
    agent = ResponsesAgent(args.model, args.reasoning_effort, args.max_turns, args.max_tool_calls)
    result = run_sample(args.dataset, args.sample_id, agent, args.reaper, args.output)
    print(json.dumps({k: result[k] for k in ("task_id", "passed", "infrastructure", "elapsed_seconds")}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
