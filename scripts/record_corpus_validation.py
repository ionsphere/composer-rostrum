"""Publish compact evidence only after checking the actual portable archive."""
import argparse
from collections import Counter
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from composer_rostrum.corpus import CORPUS_VERSION, generate_chains
from composer_rostrum.corpus_capture import sha256, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--controls", required=True, type=Path)
    parser.add_argument("--unit-results", required=True, type=Path)
    parser.add_argument("--fade-results", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads((args.capture / "dataset/validation.json").read_text(encoding="utf-8"))
    archive = json.loads((args.capture / "archive.json").read_text(encoding="utf-8"))
    controls = json.loads(args.controls.read_text(encoding="utf-8"))
    def tests(path):
        suites = list(ET.parse(path).getroot().iter("testsuite"))
        result = {key: sum(int(s.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
        assert result["tests"] > 0 and result["failures"] == result["errors"] == 0
        return result
    unit, fades = tests(args.unit_results), tests(args.fade_results)
    assert fades["tests"] == 1 and fades["skipped"] == 0
    assert report["samples"] == report["passed"] == 6 * report["chains"]
    assert report["relocated_restart_checks"] == report["chains"]
    assert all(row["ok"] for row in controls) and len(controls) == 6
    assert sha256(args.capture / archive["file"]) == archive["sha256"]
    with zipfile.ZipFile(args.capture / archive["file"]) as bundle:
        inventory = json.loads(bundle.read("checksums.json"))
        assert set(bundle.namelist()) == set(inventory) | {"checksums.json"}
        for name, expected in inventory.items():
            assert hashlib.sha256(bundle.read(name)).hexdigest() == expected, name
        states = [name for name in inventory if name.endswith("/state.json")]
        assert len(states) == report["chains"] * 7
        assert len([name for name in inventory if name.endswith("/project.rpp")]) == len(states)
        assert len([name for name in inventory if name.endswith("/render.wav")]) == report["samples"]
        class Catalog(HTMLParser):
            articles = 0
            links = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                self.articles += tag == "article"
                if tag == "a":
                    self.links.append(attrs["href"])
                if tag == "audio":
                    self.links.append(attrs["src"])
        catalog = Catalog()
        catalog.feed(bundle.read("catalog.html").decode("utf-8"))
        assert catalog.articles == report["samples"]
        assert all(link in inventory for link in catalog.links)
        for name in inventory:
            if name.startswith("private/"):
                private = json.loads(bundle.read(name))
                assert private["studio_files"]
                for relative, digest in private["studio_files"].items():
                    assert inventory[relative] == digest
                for event in private["trajectory"]:
                    result = event.get("result")
                    if isinstance(result, dict) and "path" in result and "content_hash" in result:
                        assert inventory[result["path"]] == result["content_hash"]
    manifest = {"corpus": CORPUS_VERSION, "seed": report["seed"], "chains": report["chains"], "samples": []}
    for chain in generate_chains(report["chains"], report["seed"]):
        for step in chain.steps:
            payload = json.dumps(step.task.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            manifest["samples"].append({"id": step.task.id, "chain_id": chain.id, "split": chain.split,
                "stage": step.task.tags[1], "prompt": step.task.prompt, "task_sha256": hashlib.sha256(payload).hexdigest()})
    write_json(Path("benchmarks") / f"{CORPUS_VERSION}.json", manifest)
    compact = {**report, "archive": archive, "native_states": len(states), "rendered_states": report["samples"],
               "archive_file_checksums_verified": len(inventory), "native_eval_controls": controls,
               "unit_tests": unit, "native_fade_test": fades, "catalog_links_verified": len(catalog.links),
               "stages": dict(Counter(row["stage"] for row in manifest["samples"])),
               "artifact_directory": args.capture.as_posix()}
    write_json(Path("docs/validation") / f"{CORPUS_VERSION}.json", compact)
    print(json.dumps({k: v for k, v in compact.items() if k not in ("evidence", "native_eval_controls")}, indent=2))


if __name__ == "__main__":
    main()
