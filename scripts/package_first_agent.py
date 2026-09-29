"""Bundle the first local adapter and its validation metadata for reuse."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    inputs = [(path, f"adapter/{path.name}") for path in sorted((root / "run-002/adapter").iterdir()) if path.is_file()]
    inputs.extend([
        (root / "run-002/report.json", "report.json"),
        (root / "data-final/manifest.json", "data-manifest.json"),
        (Path("docs/validation/first-local-music-agent-v1.json"), "validation.json"),
    ])
    output = root / "first-agent-adapter-v1.zip"
    with ZipFile(output, "w") as archive:
        for source, name in inputs:
            info = ZipInfo(name, date_time=(2026, 9, 27, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, source.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"{output} ({output.stat().st_size} bytes) sha256={digest}")


if __name__ == "__main__":
    main()
