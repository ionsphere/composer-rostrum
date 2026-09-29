"""Freeze dataset, model, and native evidence for music-program routing v1."""
import hashlib
import json
from pathlib import Path

from composer_rostrum.corpus_capture import write_json
from composer_rostrum.music_programs import choose_music_program, discover_music_programs


ROOT = Path("artifacts/first-agent-training")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    data = ROOT / "data-routing-v3"
    run = ROOT / "run-routing-001"
    manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    for split in ("train", "dev"):
        assert manifest["files"][split] == sha256(data / f"{split}.jsonl")
        assert report[f"{split}_sha256"] == manifest["files"][split]
    assert manifest["test_split_exported"] is False
    routing_before = report["baseline"]["by_corpus"]["music-program-routing-v1"]
    routing_after = report["adapted"]["by_corpus"]["music-program-routing-v1"]
    assert routing_after["exact"] > routing_before["exact"]
    tempo_dir = ROOT / "native-routed-tempo"
    tempo = json.loads((tempo_dir / "outcome.json").read_text(encoding="utf-8"))
    route = json.loads((tempo_dir / "route.json").read_text(encoding="utf-8"))
    assert tempo["passed"] and tempo["infrastructure"]["ok"]
    assert route["choice"]["program"] == "reaper"
    gain = json.loads((ROOT / "native-routed-adapter-gain/outcome.json").read_text(encoding="utf-8"))
    assert gain["passed"] and gain["infrastructure"]["ok"]
    adapter = run / "adapter/adapter_model.safetensors"
    none = choose_music_program(["comp_audio"], discover_music_programs())
    assert none.status == "unavailable" and none.program is None
    rows = json.loads((run / "dev-predictions.json").read_text(encoding="utf-8"))["adapted"]
    routing_failures = [{"id": row["id"], "expected": row["expected"],
                         "actual": row["actual"]} for row in rows
                        if row["id"].startswith("route-") and row["actual"] != row["expected"]]
    output = {
        "experiment": "music-program-routing-v1",
        "base_model": report["base_model"], "base_revision": report["base_revision"],
        "continued_from": "first-local-music-agent-v1",
        "adapter_sha256": sha256(adapter), "adapter_bytes": adapter.stat().st_size,
        "training_steps": report["max_steps"], "train_actions_used": report["train_examples"],
        "data_format": manifest["format"], "data_counts": manifest["counts"],
        "source_format": manifest["source_format"], "source_files": manifest["source_files"],
        "train_sha256": report["train_sha256"], "dev_sha256": report["dev_sha256"],
        "test_split_exported": False,
        "next_action_dev": {"base": {k: report["baseline"][k] for k in ("n", "parsed", "tool_correct", "action_exact")},
                            "adapted": {k: report["adapted"][k] for k in ("n", "parsed", "tool_correct", "action_exact")}},
        "routing_dev": {"base": routing_before, "adapted": routing_after,
                        "failures": routing_failures},
        "native_checks": [
            {"task_id": tempo["task_id"], "program": "reaper", "passed": tempo["passed"],
             "outcome_sha256": sha256(tempo_dir / "outcome.json")},
            {"task_id": gain["task_id"], "program": "reaper", "passed": gain["passed"],
             "outcome_sha256": sha256(ROOT / "native-routed-adapter-gain/outcome.json")},
        ],
        "current_machine_no_comping_route": none.to_dict(),
        "audacity_status": "installed; scripting connection and native runner not verified",
    }
    write_json(Path("docs/validation/music-program-routing-v1.json"), output)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
