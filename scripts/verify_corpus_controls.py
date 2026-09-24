"""Exercise native evaluation from exported inputs, never rematerializing targets."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from composer_rostrum.corpus import generate_chains
from composer_rostrum.corpus_capture import _reference, write_json
from composer_rostrum.corpus_eval import run_sample


class Control:
    def __init__(self, step, mode):
        self.step, self.mode = step, mode

    def solve(self, task, environment):
        assert task.evaluators == [], "private evaluators crossed the agent boundary"
        if self.mode == "noop":
            environment.call("render")
        elif self.mode == "wrong":
            environment.call("set_clip_fades", track_id="samples", clip_id="hit",
                             fade_in_seconds=0.0, fade_out_seconds=0.0)
            environment.call("render")
        else:
            _reference(self.step, environment)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--reaper", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    chain = generate_chains(1)[0]
    records = []
    for index, mode in [(0, "reference"), (1, "reference"), (2, "reference"), (5, "reference"), (1, "noop"), (2, "wrong")]:
        step = chain.steps[index]
        result = run_sample(args.dataset, step.task.id, Control(step, mode), args.reaper, args.output / f"{index}-{mode}")
        expected = mode == "reference"
        ok = result["infrastructure"]["ok"] and result["passed"] == expected and "agent_error" not in result.get("failure_class", "")
        records.append({"task": step.task.id, "control": mode, "passed": result["passed"], "expected": expected, "ok": ok})
        print(json.dumps(records[-1]), flush=True)
    write_json(args.output / "summary.json", records)
    raise SystemExit(0 if all(r["ok"] for r in records) else 1)


if __name__ == "__main__":
    main()
