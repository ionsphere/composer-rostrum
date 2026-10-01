"""Capture the native Audacity eval corpus through mod-script-pipe."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from composer_rostrum.backends.audacity.corpus import CASES, capture


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/audacity-corpus-v1"))
    parser.add_argument("--case", choices=[case["id"] for case in CASES],
                        help="Capture one case for incremental native validation")
    args = parser.parse_args()
    cases = [case for case in CASES if not args.case or case["id"] == args.case]
    result = capture(args.output, cases)
    print(f"Captured {result['case_count']} native Audacity eval cases in {args.output}")


if __name__ == "__main__":
    main()
