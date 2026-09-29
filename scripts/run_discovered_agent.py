"""Discover a capable program before starting a local music-agent task."""
import argparse
import json
from pathlib import Path

from composer_rostrum.backends.reaper import ReaperBackend
from composer_rostrum.local_action_agent import LocalActionAgent
from composer_rostrum.music_programs import choose_music_program, discover_music_programs
from composer_rostrum.runner import load_task, run_task


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path)
    parser.add_argument("--requires", action="append", required=True,
                        help="Canonical operation required by this intent; repeat for multiple")
    parser.add_argument("--prefer", choices=("reaper", "audacity"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--adapter", type=Path)
    args = parser.parse_args()
    task = load_task(args.task)
    programs = discover_music_programs()
    choice = choose_music_program(args.requires, programs, args.prefer)
    if choice.status != "selected":
        print(json.dumps({"task_id": task.id, "route": choice.to_dict(),
                          "programs": [program.to_dict() for program in programs]}, indent=2))
        raise SystemExit(2)
    agent = LocalActionAgent(args.model, str(args.adapter) if args.adapter else None)
    choice = agent.choose_program(task.prompt, args.requires, programs, args.prefer)
    if choice.status != "selected":
        print(json.dumps({"task_id": task.id, "route": choice.to_dict(),
                          "model_route_decision": agent.route_decision}, indent=2))
        raise SystemExit(2)
    if choice.program != "reaper":
        # A verified Audacity session needs its own project binding and runner.
        print(json.dumps({"task_id": task.id, "route": {
            "status": "unavailable", "program": None,
            "reason": "No native task runner is connected for Audacity."}}, indent=2))
        raise SystemExit(2)
    executable = next(program.executable for program in programs if program.name == choice.program)
    result = run_task(task, agent=agent, backend=ReaperBackend(executable), workspace=args.output)
    result["route"] = choice.to_dict()
    (args.output / "route.json").write_text(json.dumps({"choice": choice.to_dict(),
        "model_decision": agent.route_decision}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"task_id": task.id, "route": choice.to_dict(),
                      "passed": result["passed"], "failure_class": result.get("failure_class")}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
