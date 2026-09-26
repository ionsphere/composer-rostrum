"""Run correct, no-op, and wrong-item agents from exported clip-gain inputs."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from composer_rostrum.clip_gain_corpus import generate_clip_gain_chains
from composer_rostrum.corpus_capture import _reference, write_json
from composer_rostrum.corpus_eval import run_sample


class Control:
    def __init__(self, step, mode):
        self.step, self.mode = step, mode

    def solve(self, task, environment):
        assert not task.evaluators, "private checks crossed the agent boundary"
        if self.mode == "reference":
            _reference(self.step, environment)
        elif self.mode == "noop":
            environment.call("render")
        else:
            other = "loud" if self.step.task.tags[1] == "quiet" else "quiet"
            environment.call("set_clip_gain", track_id="samples", clip_id=other, gain_db=0.0)
            environment.call("render")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--reaper", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260925)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for step in generate_clip_gain_chains(1, args.seed)[0].steps:
        for mode in ("reference", "noop", "wrong"):
            outcome = run_sample(args.dataset, step.task.id, Control(step, mode),
                                 args.reaper, args.output / f"{step.task.id}-{mode}")
            expected = mode == "reference"
            row = {"task": step.task.id, "control": mode, "expected": expected,
                   "passed": outcome["passed"],
                   "production_audio_relation": next((x["passed"] for x in outcome["results"]
                       if x["evaluator"] == "production_audio_relation"), None)}
            row["ok"] = outcome["infrastructure"]["ok"] and row["passed"] == expected and \
                        row["production_audio_relation"] == expected
            rows.append(row)
            print(json.dumps(row), flush=True)
    write_json(args.output / "summary.json", rows)
    raise SystemExit(0 if all(row["ok"] for row in rows) else 1)


if __name__ == "__main__":
    main()
