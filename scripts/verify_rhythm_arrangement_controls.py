"""Run reference, no-op, and one-wrong-hit agents on native rhythm inputs."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from composer_rostrum.corpus_capture import _reference, write_json
from composer_rostrum.corpus_eval import run_sample
from composer_rostrum.rhythm_arrangement_corpus import generate_rhythm_arrangement_chains


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
            for index, op in enumerate(self.step.operations):
                args = dict(op["arguments"])
                if index == 1:
                    args["timeline_start_beats"] += 0.25
                environment.call(op["tool"], **args)
            environment.call("render")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--reaper", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260926)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for step in generate_rhythm_arrangement_chains(1, args.seed)[0].steps:
        for mode in ("reference", "noop", "wrong"):
            outcome = run_sample(args.dataset, step.task.id, Control(step, mode),
                                 args.reaper, args.output / f"{step.task.id}-{mode}")
            expected = mode == "reference"
            audio = next((entry["passed"] for entry in outcome["results"]
                          if entry["evaluator"] == "reference_audio_match"), None)
            relations = {entry["evaluator"]: entry["passed"] for entry in outcome["results"]
                         if entry["evaluator"] in ("rhythm_pattern", "track_alignment")}
            row = {"task": step.task.id, "control": mode, "expected": expected,
                   "passed": outcome["passed"], "reference_audio_match": audio,
                   "rhythm_relations": relations}
            row["ok"] = outcome["infrastructure"]["ok"] and row["passed"] == expected and \
                        row["reference_audio_match"] == expected and \
                        all(value == expected for value in relations.values())
            rows.append(row)
            print(json.dumps(row), flush=True)
    write_json(args.output / "summary.json", rows)
    raise SystemExit(0 if all(row["ok"] for row in rows) else 1)


if __name__ == "__main__":
    main()
