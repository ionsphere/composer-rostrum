from copy import deepcopy

from composer_rostrum.audio import write_fixture
from composer_rostrum.evaluator import evaluate
from composer_rostrum.rhythm_arrangement_corpus import generate_rhythm_arrangement_chains


def test_instrument_fixtures_are_distinct_and_owned(tmp_path):
    kick, guitar = tmp_path / "kick.wav", tmp_path / "guitar.wav"
    write_fixture(kick, 0.22, kind="kick")
    write_fixture(guitar, 0.28, kind="guitar")
    assert kick.read_bytes() != guitar.read_bytes()
    assert kick.stat().st_size > 1000 and guitar.stat().st_size > 1000


def test_linked_rhythm_and_alignment_oracles_reject_wrong_track_timing():
    chains = generate_rhythm_arrangement_chains(20)
    assert len(chains) == 20
    assert {chain.split for chain in chains} == {"train", "dev", "test"}
    for chain in chains:
        rhythm, alignment = chain.steps
        assert alignment.task.initial_project.to_dict() == rhythm.expected.to_dict()
        assert all(result.passed for result in evaluate(rhythm.task, rhythm.task.initial_project,
                                                       rhythm.expected))
        assert all(result.passed for result in evaluate(alignment.task, alignment.task.initial_project,
                                                       alignment.expected))
        wrong_kick = deepcopy(rhythm.expected)
        wrong_kick.tracks[0]["clips"][1]["timeline_start_beats"] += 0.25
        assert not all(result.passed for result in evaluate(rhythm.task, rhythm.task.initial_project,
                                                           wrong_kick))
        wrong_guitar = deepcopy(alignment.expected)
        wrong_guitar.tracks[1]["clips"][2]["timeline_start_beats"] += 0.25
        results = evaluate(alignment.task, alignment.task.initial_project, wrong_guitar)
        assert not all(result.passed for result in results)
        assert any(result.evaluator == "track_alignment" and not result.passed for result in results)
