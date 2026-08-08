from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from .agent import Agent, ReferenceAgent
from .environment import MusicEnvironment, project_hash
from .evaluator import aggregate_score, evaluate
from .models import RostrumTask


def load_task(path: str | Path) -> RostrumTask:
    with open(path, "r", encoding="utf-8") as handle:
        return RostrumTask.from_dict(json.load(handle))


def run_task(task: RostrumTask, agent: Agent | None = None) -> dict:
    before = deepcopy(task.initial_project)
    environment = MusicEnvironment(before, task.allowed_tools)
    (agent or ReferenceAgent()).solve(task, environment)
    after = environment.project
    results = evaluate(task, before, after)
    return {
        "task_id": task.id,
        "score": aggregate_score(results),
        "passed": bool(results) and all(result.passed for result in results),
        "results": [result.__dict__ for result in results],
        "project": after.to_dict(),
        "project_before_hash": project_hash(before),
        "project_after_hash": project_hash(after),
        "trajectory": [event.to_dict() for event in environment.trajectory],
        "tool_calls": len(environment.trajectory),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Composer Rostrum benchmark task")
    parser.add_argument("task", help="Path to a Rostrum task JSON file")
    args = parser.parse_args()
    outcome = run_task(load_task(args.task))
    print(json.dumps(outcome, indent=2))
    raise SystemExit(0 if outcome["passed"] else 1)


if __name__ == "__main__":
    main()
