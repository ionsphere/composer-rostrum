import json
import pytest
from composer_rostrum.backends.base import BackendError
from composer_rostrum.backends.reaper import ReaperBackend
from composer_rostrum.backends.reaper.transport import FileBridgeTransport
from composer_rostrum.daw_tasks import phrase_project


@pytest.mark.parametrize("payload", ['not json', '[]', '{"protocol":1,"id":"000001","ok":"yes"}', '{"protocol":2,"id":"000001","ok":true}'])
def test_corrupt_responses_poison_transport(tmp_path, payload):
    transport = FileBridgeTransport(tmp_path)
    identity, _ = transport.prepare_request("ping")
    (tmp_path / "responses" / f"{identity}.json").write_text(payload)
    with pytest.raises(BackendError):
        transport.await_response(identity, timeout=0.1)
    with pytest.raises(BackendError, match="unusable"):
        transport.prepare_request("save")


def test_timeout_requires_new_worker(tmp_path):
    transport = FileBridgeTransport(tmp_path, poll_interval=0.001)
    with pytest.raises(BackendError, match="timed out"):
        transport.request("ping", timeout=0.01)
    with pytest.raises(BackendError, match="unusable"):
        transport.request("materialize")


def test_feedback_routing_and_unsupported_effects_are_rejected():
    p = phrase_project()
    p.tracks[0]["sends"] = [{"destination_id": "keys", "gain_db": 0}]
    with pytest.raises(BackendError, match="routing"):
        ReaperBackend.validate(p)
    p.tracks[0].pop("sends")
    p.tracks[0]["effects"] = [{"id": "compressor", "type": "compression"}]
    with pytest.raises(BackendError, match="gain effects"):
        ReaperBackend.validate(p)


def test_invalid_ids_and_note_bounds_are_rejected():
    p = phrase_project()
    p.tracks[0]["id"] = "../outside"
    with pytest.raises(BackendError, match="stable ID"):
        ReaperBackend.validate(p)
    p = phrase_project()
    p.tracks[0]["clips"][0]["notes"][0]["duration"] = 100
    with pytest.raises(BackendError, match="inside"):
        ReaperBackend.validate(p)


def test_worker_crash_fails_without_waiting_for_timeout(tmp_path):
    def crashed():
        raise BackendError("worker exited")
    transport = FileBridgeTransport(tmp_path, health_check=crashed)
    with pytest.raises(BackendError, match="worker exited"):
        transport.request("ping", timeout=30)
    assert transport.failed


def test_worker_owner_lock_and_failed_launch_cleanup(tmp_path):
    from composer_rostrum.backends.reaper.worker import ReaperWorker
    worker = ReaperWorker(tmp_path / "missing.exe", tmp_path)
    (tmp_path / "worker.lock").write_text("another owner")
    with pytest.raises(BackendError, match="owner"):
        worker.start()
    assert (tmp_path / "worker.lock").read_text() == "another owner"
    (tmp_path / "worker.lock").unlink()
    with pytest.raises(BackendError, match="not found"):
        worker.start()
    assert not (tmp_path / "worker.lock").exists()


def test_uncertain_request_workspace_cannot_be_resumed(tmp_path):
    backend = ReaperBackend(executable="missing.exe")
    native = backend.materialize(phrase_project(), tmp_path)
    (tmp_path / "requests/000001.json").write_text('{}')
    with pytest.raises(BackendError, match="unacknowledged"):
        backend.open(native, resume=True)


def test_all_daw_fixtures_satisfy_strict_native_subset():
    from composer_rostrum.daw_tasks import generate_daw_suite
    for task in generate_daw_suite():
        ReaperBackend.validate(task.initial_project)


def test_invalid_native_edit_is_recoverable_without_mutation():
    from composer_rostrum.backends.reaper.backend import ReaperEnvironment
    from composer_rostrum.environment import ToolError
    class Backend:
        validate = staticmethod(ReaperBackend.validate)
        def readback(self, session):
            return phrase_project()
        def _write_project(self, *args):
            raise AssertionError("invalid edit reached native worker")
    env = ReaperEnvironment(Backend(), None, ["set_note_start", "inspect_project"])
    with pytest.raises(ToolError, match="960 ticks"):
        env.call("set_note_start", track_id="keys", clip_id="phrase", note_id="n0", start=0.13)
    assert env.trajectory[-1].before_hash == env.trajectory[-1].after_hash
    assert env.call("inspect_project")["tracks"][0]["clips"][0]["notes"][0]["start"] == 0
