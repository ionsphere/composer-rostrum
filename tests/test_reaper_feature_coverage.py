import json
from pathlib import Path


def test_coverage_ledger_has_unique_features_and_evidence():
    root = Path(__file__).resolve().parents[1]
    ledger = json.loads((root / "benchmarks/reaper-feature-coverage-v1.json").read_text(encoding="utf-8"))
    features = ledger["features"]
    assert len(features) >= 60
    assert len({f["id"] for f in features}) == len(features)
    assert len({f["area"] for f in features}) >= 9
    assert {f["status"] for f in features} == {"native_verified", "partial", "open", "external"}
    for feature in features:
        assert feature["id"] and feature["intent"]
        assert ("evidence" in feature) == (feature["status"] == "native_verified")
        if "evidence" in feature:
            corpus = feature["evidence"].split(":", 1)[0]
            assert corpus in {"reaper-chains-v1", "reaper-item-edits-v1"}
