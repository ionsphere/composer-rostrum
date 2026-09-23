from dataclasses import replace
from pathlib import Path
from composer_rostrum.backends.base import RenderArtifact, RenderRequest
from composer_rostrum.daw_tasks import generate_daw_suite
from composer_rostrum.environment import project_hash, TrajectoryEvent
from composer_rostrum.render_evaluator import evaluate_renders


def test_daw_suite_counts_and_feedback_preservation():
    from collections import Counter
    tasks = generate_daw_suite()
    assert len(tasks) == len({t.id for t in tasks}) == 20
    assert set(Counter(t.initial_project.metadata["family"] for t in tasks).values()) == {5}
    assert sum(t.execution_level == "E3" for t in tasks) == 5
    assert all("offline_render" in t.required_capabilities for t in tasks)


def test_feedback_requires_observation_before_edit_and_fresh_final_render():
    task = generate_daw_suite()[-5]
    before = task.initial_project
    after = replace(before, tracks=[{**before.tracks[0], "gain_db": 5.0}])
    h1, h2 = project_hash(before), project_hash(after)
    def artifact(identity, h, rms):
        return RenderArtifact(identity, "test", h, Path(identity+".wav"), identity, RenderRequest(),
                              metrics={"silent": False, "rms_dbfs": rms})
    a, b = artifact("r1", h1, -40), artifact("r2", h2, -24)
    observe = TrajectoryEvent(1, "analyze_render", {"render_id": "r1"}, {}, h1, h1, [])
    edit = TrajectoryEvent(2, "set_track_gain", {}, {}, h1, h2, ["tracks.0.gain_db"])
    render = TrajectoryEvent(3, "render", {}, {"render_id": "r2"}, h2, h2, [])
    assert all(r.passed for r in evaluate_renders(task, [a,b], [observe,edit,render], after))
    assert not all(r.passed for r in evaluate_renders(task, [a,b], [edit,render], after))
    assert not all(r.passed for r in evaluate_renders(task, [a,b], [replace(observe,index=4),edit,render], after))
    assert not all(r.passed for r in evaluate_renders(task, [a,replace(b,project_hash=h1)], [observe,edit,render], after))
