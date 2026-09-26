from composer_rostrum.clip_gain_corpus import generate_clip_gain_chains


def test_gain_chain_has_linked_revisions_and_item_only_changes():
    chains = generate_clip_gain_chains(20)
    assert len(chains) == 20
    assert {chain.split for chain in chains} == {"train", "dev", "test"}
    for chain in chains:
        first, second = chain.steps
        assert second.task.initial_project.to_dict() == first.expected.to_dict()
        before = first.task.initial_project.tracks[0]
        after = second.expected.tracks[0]
        assert before["gain_db"] == after["gain_db"] == 0
        assert before["effects"] == after["effects"] == []
        assert [clip["gain_db"] for clip in before["clips"]] != [0, 0]
        assert [clip["gain_db"] for clip in after["clips"]] == [0, 0]
        assert all(step.task.execution_level == "E2" for step in chain.steps)
