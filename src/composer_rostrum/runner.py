from __future__ import annotations

import argparse
import json
import tempfile
import uuid
import time
from copy import deepcopy
from pathlib import Path

from .agent import Agent, ReferenceAgent
from .backends.base import DawBackend, BackendError
from .backends.memory import InMemoryBackend
from .environment import project_hash
from .evaluator import aggregate_score, evaluate
from .models import RostrumTask


def load_task(path: str | Path) -> RostrumTask:
    with open(path, "r", encoding="utf-8") as handle:
        return RostrumTask.from_dict(json.load(handle))


def run_task(task: RostrumTask, agent: Agent | None = None, backend: DawBackend | None = None,
             workspace: str | Path | None = None) -> dict:
    selected = backend or InMemoryBackend()
    selected.capabilities.require(task.required_capabilities)
    before = deepcopy(task.initial_project)
    # Native sessions and immutable audio must outlive this function.
    temp = None
    if workspace is None and selected.name == "memory":
        temp = tempfile.TemporaryDirectory(prefix="rostrum-")
        directory = Path(temp.name)
    else:
        directory = Path(workspace) if workspace is not None else Path("artifacts") / uuid.uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    session = environment = None
    agent_started = False
    outcome = {"task_id": task.id, "level": task.level, "execution_level": task.execution_level,
               "family": before.metadata.get("family", "unknown"), "score": 0.0, "passed": False,
               "results": [], "trajectory": [], "renders": [], "tool_calls": 0,
               "project_before_hash": project_hash(before), "infrastructure": {"ok": True, "error": None},
               "backend": {"name": selected.name, "version": selected.version,
                           "capabilities": selected.capabilities.to_dict()}}
    try:
        native = selected.materialize(before, directory)
        session = selected.open(native)
        session.state.get("capabilities", selected.capabilities).require(task.required_capabilities)
        environment = selected.create_environment(session, task.allowed_tools)
        # Evaluators/oracles never cross the agent boundary.
        public_task = deepcopy(task)
        public_task.evaluators = []
        agent_started = True
        (agent or ReferenceAgent()).solve(public_task, environment)
        selected.commit_environment(session, environment)
        selected.save(session)
        after = selected.readback(session)
        results = evaluate(task, before, after)
        from .render_evaluator import evaluate_renders
        results.extend(evaluate_renders(task, session.state.get("renders", []), environment.trajectory, after))
        outcome.update(score=aggregate_score(results), passed=bool(results) and all(r.passed for r in results),
                       results=[r.__dict__ for r in results], project=after.to_dict(), project_after_hash=project_hash(after))
        def dimension(predicate):
            matching = [r for r in results if predicate(r.evaluator)]
            return all(r.passed for r in matching) if matching else None
        outcome["dimensions"] = {
            "semantic": dimension(lambda n: not n.startswith(("preserve", "render_", "feedback_"))),
            "preservation": dimension(lambda n: n.startswith("preserve")),
            "render": dimension(lambda n: n.startswith("render_")),
            "feedback": dimension(lambda n: n.startswith("feedback_")),
        }
    except BackendError as exc:
        outcome["infrastructure"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        outcome["failure_class"] = "infrastructure"
    except Exception as exc:
        outcome["failure_class"] = "agent_error"
        outcome["agent_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if environment is not None:
            outcome.update(trajectory=[e.to_dict() for e in environment.trajectory], tool_calls=len(environment.trajectory))
        if agent_started and agent is not None and hasattr(agent, "usage"):
            outcome["model_usage"] = deepcopy(agent.usage)
            outcome["model_responses"] = deepcopy(agent.responses)
        if session is not None:
            outcome["renders"] = [r.to_dict() for r in session.state.get("renders", [])]
            selected.close(session)
        outcome["elapsed_seconds"] = time.monotonic() - started
        if not outcome["passed"] and "failure_class" not in outcome:
            failed = [r["evaluator"] for r in outcome["results"] if not r["passed"]]
            outcome["failure_class"] = ("preservation" if any("preserv" in r for r in failed) else
                "render" if any(r.startswith("render_") for r in failed) else
                "feedback" if any(r.startswith("feedback_") for r in failed) else "semantic")
        if temp is None:
            outcome["workspace"] = str(directory.resolve())
            (directory / "outcome.json").write_text(json.dumps(outcome, indent=2), encoding="utf-8")
        else:
            temp.cleanup()
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Composer Rostrum benchmark task")
    parser.add_argument("task", help="Path to a Rostrum task JSON file")
    parser.add_argument("--reaper", help="REAPER executable for native execution")
    parser.add_argument("--output", type=Path, help="New persistent run directory")
    args = parser.parse_args()
    from .backends.reaper import ReaperBackend
    outcome = run_task(load_task(args.task), backend=ReaperBackend(args.reaper) if args.reaper else None, workspace=args.output)
    print(json.dumps(outcome, indent=2))
    raise SystemExit(0 if outcome["passed"] else 1)


if __name__ == "__main__":
    main()
