"""Run all twenty native acceptance tasks; preserve each worker's evidence."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from composer_rostrum.backends.reaper import ReaperBackend
from composer_rostrum.daw_tasks import DawReferenceAgent, generate_daw_suite
from composer_rostrum.runner import run_task
from composer_rostrum.benchmark import summarize

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reaper", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task", help="Optional task ID for targeted regression")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    outcomes = []
    for task in generate_daw_suite():
        if args.task and task.id != args.task:
            continue
        result = run_task(task, DawReferenceAgent(), ReaperBackend(args.reaper, timeout=60), args.output / task.id)
        outcomes.append(result)
        print(task.id, result["passed"], result.get("failure_class", "passed"), flush=True)
        if not result["infrastructure"]["ok"]:
            print(result["infrastructure"]["error"], flush=True)
    report = summarize(outcomes)
    (args.output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if outcomes and all(r["passed"] for r in outcomes) else 1)

if __name__ == "__main__":
    main()
