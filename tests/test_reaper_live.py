"""Opt-in tests: an absent REAPER installation is a skip, never a fake pass."""
import os
import pytest
from composer_rostrum.backends.reaper import ReaperBackend
from composer_rostrum.backends.base import DawOperation, RenderRequest
from composer_rostrum.daw_tasks import phrase_project, generate_daw_suite, DawReferenceAgent
from composer_rostrum.runner import run_task

pytestmark = [pytest.mark.reaper, pytest.mark.skipif(not os.environ.get("REAPER_EXECUTABLE"), reason="REAPER_EXECUTABLE not configured")]


def test_real_audio_edit_identity_restart_and_determinism(tmp_path):
    backend = ReaperBackend(timeout=60)
    native = backend.materialize(phrase_project(), tmp_path)
    session = backend.open(native)
    try:
        ids = backend._request(session, "native_ids")
        a = backend.render(session, RenderRequest())
        assert not a.metrics["silent"]
        backend.execute(session, DawOperation("set_note_pitch", {"track_id":"keys", "clip_id":"phrase", "note_id":"n0", "pitch":62}))
        expected = backend.readback(session).to_dict()
        assert expected["tracks"][0]["clips"][0]["notes"][0]["pitch"] == 62
        assert backend._request(session, "native_ids") == ids
        b = backend.render(session, RenderRequest())
        assert a.metrics["pcm_hash"] != b.metrics["pcm_hash"] and not b.metrics["silent"]
        backend.close(session)
        session = backend.open(native, resume=True)
        assert backend.readback(session).to_dict() == expected
        assert backend._request(session, "native_ids") == ids
        c = backend.render(session, RenderRequest())
        assert b.metrics["pcm_hash"] == c.metrics["pcm_hash"]
        assert a.path.exists() and b.path.exists() and c.path.exists()
    finally:
        backend.close(session)


@pytest.mark.parametrize("index", range(20))
def test_real_daw_acceptance_suite(tmp_path, index):
    outcome = run_task(generate_daw_suite()[index], DawReferenceAgent(), ReaperBackend(timeout=60), tmp_path / "run")
    assert outcome["passed"], outcome
