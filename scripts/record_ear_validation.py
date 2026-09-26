"""Freeze deterministic-ear control outcomes from two native corpus suites."""
import argparse
import hashlib
import json
from pathlib import Path

from composer_rostrum.corpus_capture import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("creation_controls", type=Path)
    parser.add_argument("item_controls", type=Path)
    parser.add_argument("--extra", type=Path, action="append", default=[], help="Additional reference outcome.json")
    args = parser.parse_args()
    rows = []
    for suite, root in (("creation", args.creation_controls), ("item_edits", args.item_controls)):
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        assert all(row["ok"] for row in summary)
        for control in summary:
            # Summary rows identify the control; locate the matching outcome by content.
            matches = []
            for path in root.glob("*/outcome.json"):
                outcome = json.loads(path.read_text(encoding="utf-8"))
                if outcome["task_id"] == control["task"] and path.parent.name.endswith("-" + control["control"]):
                    matches.append((path.parent, outcome))
            assert len(matches) == 1
            folder, outcome = matches[0]
            reference = [result for result in outcome["results"] if result["evaluator"] == "reference_audio_match"]
            relation = [result for result in outcome["results"] if result["evaluator"] == "item_audio_relation"]
            if control["task"].endswith("feedback"):
                assert not reference
            else:
                assert len(reference) == 1
            if suite == "item_edits":
                assert len(relation) == 1
            comparison_path = folder / "audio-comparison.json"
            comparison = json.loads(comparison_path.read_text(encoding="utf-8")) if comparison_path.exists() else None
            if comparison is not None:
                assert comparison["verdict"]["passed"] == reference[0]["passed"]
            rows.append({"suite": suite, "task": outcome["task_id"], "control": control["control"],
                         "expected_pass": control["expected"], "actual_pass": outcome["passed"],
                         "reference_audio_match": reference[0]["passed"] if reference else None,
                         "item_audio_relation": relation[0]["passed"] if relation else None,
                         "waveform_snr_db": comparison["difference"]["waveform_snr_db"] if comparison else None})
    for path in args.extra:
        outcome = json.loads(path.read_text(encoding="utf-8"))
        reference = [result for result in outcome["results"] if result["evaluator"] == "reference_audio_match"]
        assert outcome["passed"] and len(reference) == 1 and reference[0]["passed"]
        comparison = json.loads((path.parent / "audio-comparison.json").read_text(encoding="utf-8"))
        assert comparison["verdict"]["passed"]
        rows.append({"suite": "creation", "task": outcome["task_id"], "control": "reference",
                     "expected_pass": True, "actual_pass": True, "reference_audio_match": True,
                     "item_audio_relation": None,
                     "waveform_snr_db": comparison["difference"]["waveform_snr_db"]})
    report = {"validation": "deterministic-ear-v1", "native_control_runs": len(rows),
              "ear_source_lf_sha256": hashlib.sha256(Path("src/composer_rostrum/ear.py")
                  .read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
              "fixed_target_rule": {"kind": "same", "min_snr_db": 70, "duration_tolerance_ms": 1},
              "all_expected_outcomes": all(row["expected_pass"] == row["actual_pass"] for row in rows),
              "fixed_target_audio_checks": sum(row["reference_audio_match"] is not None for row in rows),
              "item_audio_relation_checks": sum(row["item_audio_relation"] is not None for row in rows),
              "model_runs": "not_run", "controls": rows}
    assert report["all_expected_outcomes"] and report["native_control_runs"] == 10 + len(args.extra)
    write_json(Path("docs/validation/deterministic-ear-v1.json"), report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
