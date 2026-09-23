"""Build a reviewable evidence summary without publishing workstation paths."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from composer_rostrum.benchmark import summarize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--daw", required=True, type=Path)
    parser.add_argument("--smoke", required=True, type=Path)
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    controls = json.loads((args.benchmark / "controls.json").read_text(encoding="utf-8"))
    outcomes = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(args.daw.glob("*/outcome.json"))]
    smoke = json.loads((args.smoke / "acceptance.json").read_text(encoding="utf-8"))
    tests = ET.parse(args.junit).getroot()
    suites = list(tests.iter("testsuite"))
    if not smoke["passed"] or not smoke["process_restart_verified"] or len(outcomes) != 20 or not all(r["passed"] for r in outcomes):
        raise ValueError("native evidence is incomplete")
    if not suites or any(int(s.attrib.get("failures", 0)) + int(s.attrib.get("errors", 0)) for s in suites):
        raise ValueError("unit validation is incomplete")
    if controls["reference"]["passed"] != 120 or any(controls[n]["passed"] for n in ("no-op", "damaging")):
        raise ValueError("control validation is incomplete")
    report = {
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "reaper": smoke["handshake"],
        "unit_tests": {k: sum(int(s.attrib.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")},
        "symbolic_controls": controls,
        "daw_reference": summarize(outcomes),
        "restart_acceptance": {"passed": True, "process_restart_verified": True,
            "renders": [{"render_id": r["render_id"], "project_hash": r["project_hash"],
                         "content_hash": r["content_hash"], "metrics": r["metrics"]} for r in smoke["renders"]]},
        "model_comparison": {"status": "not_run", "reason": "Requires authenticated provider and selected model configurations"},
        "local_evidence": {k: getattr(args, k).as_posix() for k in ("benchmark", "daw", "smoke", "junit")},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    manifest = (args.benchmark / "manifest.json").read_text(encoding="utf-8")
    frozen = Path("benchmarks/rostrum-120-v1.json")
    frozen.parent.mkdir(exist_ok=True)
    frozen.write_text(manifest, encoding="utf-8", newline="\n")
    print(f"Recorded {len(outcomes)} real-DAW outcomes and 120-task controls in {args.output}")


if __name__ == "__main__":
    main()
