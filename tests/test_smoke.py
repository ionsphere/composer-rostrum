from composer_rostrum.runner import load_task, run_task


def test_seed_task_passes():
    task = load_task("examples/tasks/L0-001-set-tempo.json")
    outcome = run_task(task)
    assert outcome["passed"] is True
    assert outcome["score"] == 1.0
    assert outcome["project"]["tempo"] == 128.0
