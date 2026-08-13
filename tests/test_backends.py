import json

import pytest

from composer_rostrum.backends import CapabilityError, InMemoryBackend, RenderRequest, RenderUnavailableError
from composer_rostrum.backends.reaper import ReaperBackend
from composer_rostrum.generator import generate_suite
from composer_rostrum.runner import run_task


def test_runner_uses_backend_lifecycle_and_reports_it():
    task = generate_suite(count=1)[0]
    outcome = run_task(task, backend=InMemoryBackend())
    assert outcome["passed"] is True
    assert outcome["backend"]["name"] == "memory"
    assert outcome["backend"]["version"] == "1"
    assert outcome["backend"]["capabilities"]["readback"] is True
    assert outcome["renders"] == []
    assert outcome["infrastructure"]["ok"] is True


def test_capability_requirements_fail_before_agent_execution():
    task = generate_suite(count=1)[0]
    task.required_capabilities = ["offline_render"]
    task.execution_level = "E2"
    with pytest.raises(CapabilityError):
        run_task(task, backend=InMemoryBackend())


def test_memory_backend_refuses_to_fake_audio(tmp_path):
    task = generate_suite(count=1)[0]
    backend = InMemoryBackend()
    native = backend.materialize(task.initial_project, tmp_path)
    session = backend.open(native)
    try:
        with pytest.raises(RenderUnavailableError):
            backend.render(session, RenderRequest())
    finally:
        backend.close(session)


def test_reaper_bootstrap_materializes_worker_bundle(tmp_path):
    task = generate_suite(count=1)[0]
    backend = ReaperBackend()
    native = backend.materialize(task.initial_project, tmp_path)

    assert native.project_path.name == "project.rpp"
    assert native.project_path.exists() is False
    assert (tmp_path / "project.music-ir.json").exists()
    assert (tmp_path / "requests").is_dir()
    assert (tmp_path / "responses").is_dir()
    assert (tmp_path / "renders").is_dir()

    manifest = json.loads(native.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "awaiting-reaper-worker"
    assert manifest["bridge_protocol"] == 1
    assert manifest["implemented_capabilities"]["offline_render"] is False
    assert manifest["target_capabilities"]["offline_render"] is True


def test_reaper_bootstrap_does_not_claim_worker_connection(tmp_path):
    task = generate_suite(count=1)[0]
    backend = ReaperBackend()
    session = backend.open(backend.materialize(task.initial_project, tmp_path))
    try:
        with pytest.raises(Exception, match="worker is not connected"):
            backend.create_environment(session, task.allowed_tools)
    finally:
        backend.close(session)
