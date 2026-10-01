"""Bundle the first local adapter and its validation metadata for reuse."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--run", default="run-002")
    parser.add_argument("--data", default="data-final")
    parser.add_argument("--validation", type=Path,
                        default=Path("docs/validation/first-local-music-agent-v1.json"))
    parser.add_argument("--name", default="first-agent-adapter-v1.zip")
    args = parser.parse_args()
    root = args.root.resolve()
    inputs = [(path, f"adapter/{path.name}") for path in sorted((root / args.run / "adapter").iterdir()) if path.is_file()]
    inputs.extend([
        (root / args.run / "report.json", "report.json"),
        (root / args.data / "manifest.json", "data-manifest.json"),
        (args.validation, "validation.json"),
    ])
    output = root / args.name
    with ZipFile(output, "w") as archive:
        for source, name in inputs:
            info = ZipInfo(name, date_time=(2026, 9, 27, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            content = source.read_bytes()
            if source.suffix in {".json", ".md", ".txt", ".jinja"}:
                content = content.replace(b"\r\n", b"\n")
            archive.writestr(info, content)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"{output} ({output.stat().st_size} bytes) sha256={digest}")


if __name__ == "__main__":
    main()
