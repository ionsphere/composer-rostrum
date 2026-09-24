"""Real REAPER acceptance probe. Artifacts remain available after worker shutdown."""
from __future__ import annotations
import argparse
import json
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from composer_rostrum.backends.reaper import ReaperBackend
from composer_rostrum.backends.base import DawOperation, RenderRequest
from composer_rostrum.models import MusicProject


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reaper", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--visible", action="store_true", help="Show first-run REAPER dialogs for diagnosis")
    parser.add_argument("--timeout", type=float, default=45)
    args = parser.parse_args()
    if args.visible:
        os.environ["ROSTRUM_REAPER_VISIBLE"] = "1"
    project = MusicProject(tracks=[{"id": "keys", "name": "Keys", "kind": "midi", "gain_db": 0.0,
        "clips": [{"id": "phrase", "kind": "midi", "start": 0.0, "length": 4.0,
                   "notes": [{"id": f"n{i}", "pitch": p, "start": float(i), "duration": 0.75,
                              "velocity": 90} for i, p in enumerate([60, 64, 67, 72])]}]}])
    backend = ReaperBackend(args.reaper, timeout=args.timeout)
    native = backend.materialize(project, args.output)
    session = backend.open(native)
    try:
        assert backend.readback(session).to_dict() == project.to_dict()
        initial_ids = backend._request(session, "native_ids")
        first = backend.render(session, RenderRequest())
        assert not first.metrics["silent"]
        backend.execute(session, DawOperation("set_note_pitch", {"track_id": "keys", "clip_id": "phrase", "note_id": "n0", "pitch": 62}))
        after = backend.readback(session)
        assert backend._request(session, "native_ids") == initial_ids
        expected = project.to_dict()
        expected["tracks"][0]["clips"][0]["notes"][0]["pitch"] = 62
        assert after.to_dict() == expected
        backend.save(session)
        backend._request(session, "reopen")
        assert backend.readback(session).to_dict() == expected
        assert backend._request(session, "native_ids") == initial_ids
        second = backend.render(session, RenderRequest())
        assert not second.metrics["silent"] and first.metrics["pcm_hash"] != second.metrics["pcm_hash"]
        assert first.project_hash != second.project_hash
        backend.save(session)
        backend.close(session)
        session = backend.open(native, resume=True)
        assert backend.readback(session).to_dict() == expected
        third = backend.render(session, RenderRequest())
        assert second.metrics["pcm_hash"] == third.metrics["pcm_hash"], "audio samples changed across process restart"
        result = {"passed": True, "process_restart_verified": True, "handshake": session.state["handshake"],
                  "renders": [first.to_dict(), second.to_dict(), third.to_dict()]}
        (args.output / "acceptance.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        backend.close(session)


if __name__ == "__main__":
    main()
