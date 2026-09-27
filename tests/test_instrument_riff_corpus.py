from copy import deepcopy

from composer_rostrum.backends.reaper import ReaperBackend
from composer_rostrum.environment import MusicEnvironment
from composer_rostrum.evaluator import evaluate
from composer_rostrum.instrument_riff_corpus import generate_instrument_riff_chains


def test_linked_instrument_and_riff_cases_are_native_valid_and_discriminating():
    chains = generate_instrument_riff_chains()
    assert len(chains) == 20
    assert [sum(c.split == split for c in chains) for split in ("train", "dev", "test")] == [12, 4, 4]
    assert all(len(chain.steps) == 4 for chain in chains)
    for chain in chains:
        for step in chain.steps:
            assert step.task.initial_project.assets == step.expected.assets == []
            ReaperBackend.validate(step.task.initial_project)
            ReaperBackend.validate(step.expected)
            env = MusicEnvironment(step.task.initial_project, step.task.allowed_tools)
            for op in step.operations:
                env.call(op["tool"], **op["arguments"])
            assert env.project.to_dict() == step.expected.to_dict()
            assert all(r.passed for r in evaluate(step.task, step.task.initial_project, env.project))
            assert not all(r.passed for r in evaluate(step.task, step.task.initial_project,
                                                       step.task.initial_project))
        swap = chain.steps[2]
        add_b = chain.steps[1]
        alternative_ids = deepcopy(add_b.expected)
        for index, note in enumerate(alternative_ids.tracks[1]["clips"][0]["notes"]):
            note["id"] = f"player-{index}"
        assert all(r.passed for r in evaluate(add_b.task, add_b.task.initial_project, alternative_ids))
        wrong_patch = deepcopy(swap.expected)
        wrong_patch.tracks[1]["instruments"][0]["patch"] = "organ"
        assert not all(r.passed for r in evaluate(swap.task, swap.task.initial_project, wrong_patch))
        riff = chain.steps[3]
        equivalent = deepcopy(riff.expected)
        for track in equivalent.tracks:
            for index, note in enumerate(track["clips"][1]["notes"]):
                note["id"] = f"own-{index}"
            track["clips"][1]["notes"].reverse()
        assert all(r.passed for r in evaluate(riff.task, riff.task.initial_project, equivalent))
        wrong_note = deepcopy(riff.expected)
        wrong_note.tracks[1]["clips"][1]["notes"][0]["pitch"] += 1
        assert not all(r.passed for r in evaluate(riff.task, riff.task.initial_project, wrong_note))
