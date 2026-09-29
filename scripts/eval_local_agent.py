"""Run a base or adapted local model on a checksum-verified native corpus input."""
import argparse
import json
from pathlib import Path

from composer_rostrum.corpus_capture import write_json
from composer_rostrum.corpus_eval import run_sample
from composer_rostrum.local_action_agent import LocalActionAgent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("sample_id")
    parser.add_argument("--reaper", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--max-turns", type=int, default=12)
    args = parser.parse_args()
    agent = LocalActionAgent(args.model, str(args.adapter) if args.adapter else None,
                             max_turns=args.max_turns)
    result = run_sample(args.dataset, args.sample_id, agent, args.reaper, args.output)
    write_json(args.output / "model-decisions.json", agent.decisions)
    print(json.dumps({"sample_id": args.sample_id, "passed": result["passed"],
                      "failure_class": result.get("failure_class"),
                      "decisions": len(agent.decisions)}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
