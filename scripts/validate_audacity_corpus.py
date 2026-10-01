"""Independently validate a captured Audacity corpus without launching Audacity."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from composer_rostrum.backends.audacity.corpus import validate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/audacity-validation-v1"))
    args = parser.parse_args()
    report = validate(args.corpus, args.output)
    print(f"Validated {report['case_count']} Audacity cases; passed={report['passed']}")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
