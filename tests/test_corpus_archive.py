import json
from pathlib import Path
import zipfile

from composer_rostrum.corpus_archive import package_dataset
from composer_rostrum.corpus_capture import sha256, write_json


def test_archive_keeps_referenced_audio_and_excludes_abandoned_attempts(tmp_path):
    dataset = tmp_path / "dataset"
    for state in ("before", "after", "abandoned"):
        folder = dataset / "states" / state
        folder.mkdir(parents=True)
        (folder / "project.rpp").write_text("test-native-state")
        write_json(folder / "project.music-ir.json", {})
        write_json(folder / "state.json", {})
    (dataset / "states/after/render.wav").write_bytes(b"final-render")
    intermediate = tmp_path / "workers/render.wav"
    intermediate.parent.mkdir()
    intermediate.write_bytes(b"intermediate-render")
    row = {"id": "sample", "input": "inputs/sample.json", "private_target": "private/sample.json", "split": "test", "stage": "feedback"}
    write_json(dataset / row["input"], {"prompt": "<script>unsafe</script>", "input_state": "states/before"})
    write_json(dataset / row["private_target"], {"target_state": "states/after", "trajectory": [
        {"result": {"path": ".\\workers\\render.wav", "content_hash": sha256(intermediate)}},
        {"result": {"path": "not-needed.wav", "content_hash": sha256(dataset / "states/after/render.wav")}}]})
    (dataset / "samples.jsonl").write_text(json.dumps(row) + "\n")
    (dataset / "README.md").write_text("test")
    write_json(dataset / "validation.json", {})
    archive = package_dataset(tmp_path)
    for _ in range(2):  # Repackaging must not require the original worker paths.
        with zipfile.ZipFile(archive) as bundle:
            inventory = json.loads(bundle.read("checksums.json"))
            assert set(bundle.namelist()) == set(inventory) | {"checksums.json"}
            assert not any("abandoned" in name or "workers/" in name for name in inventory)
            private = json.loads(bundle.read(row["private_target"]))
            for event in private["trajectory"]:
                assert event["result"]["path"] in inventory
            assert private["trajectory"][1]["result"]["path"] == "states/after/render.wav"
            catalog = bundle.read("catalog.html").decode()
            assert "<script>unsafe</script>" not in catalog
            assert "&lt;script&gt;unsafe&lt;/script&gt;" in catalog
        intermediate.unlink(missing_ok=True)
        archive = package_dataset(tmp_path)
