from __future__ import annotations

import argparse
import json
import tempfile
from copy import deepcopy
from pathlib import Path

from .agent import Agent, ReferenceAgent
from .backends.base import DawBackend
from .backends.memory import InMemoryBackend
from .environment import project_hash
from .evaluator import aggregate_score, evaluate
from .models import RostrumTask


def load_task(path: str | Path) -> RostrumTask:
    with open(path, "r", encoding="utf-8") as handle:
        return RostrumTask.from_dict(json.load(handle))


def run_task(task: RostrumTask, agent: Agent | None = None, backend: DawBackend | None = None) -> dict:
    selected = backend or InMemoryBackend()
    selected.capabilities.require(task.required_capabilities)
    before = deepcopy(task.initial_project)

    with tempfile.TemporaryDirectory(prefix=f"rostrum-{task.id}-") as temp_dir:
        native = selected.materialize(before, Path(temp_dir))
        session = selected.open(native)
        try:
            environment = selected.create_environment(session, task.allowed_tools)
            (agent or ReferenceAgent()).solve(task, environment)
            selected.commit_environment(session, environment)
            selected.save(session)
            after = selected.readback(session)
            results = evaluate(task, before, after)
            return {
                "task_id": task.id,
                "level": task.level,
                "execution_level": task.execution_level,
                "backend": {
                    "name": selected.name,
                    "version": selected.version,
                    "capabilities": selected.capabilities.to_dict(),
                },
                "score": aggregate_score(results),
                "passed": bool(results) and all(result.passed for result in results),
                "results": [result.__dict__ for result in results],
                "project": after.to_dict(),
                "project_before_hash": project_hash(before),
                "project_after_hash": project_hash(after),
                "trajectory": [event.to_dict() for event in environment.trajectory],
                "tool_calls": len(environment.trajectory),
                "renders": [],
                "infrastructure": {"ok": True, "error": None},
            }
        finally:
            selected.close(session)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Composer Rostrum benchmark task")
    parser.add_argument("task", help="Path to a Rostrum task JSON file")
    args = parser.parse_args()
    outcome = run_task(load_task(args.task))
    print(json.dumps(outcome, indent=2))
    raise SystemExit(0 if outcome["passed"] else 1)


if __name__ == "__main__":
    main()
