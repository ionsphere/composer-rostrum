"""Native REAPER item-edit chains, separate from the frozen creation corpus."""
from __future__ import annotations

from copy import deepcopy
import random

from .corpus import CorpusChain, CorpusStep, operation
from .environment import MusicEnvironment, _diff_paths
from .models import MusicProject, RostrumTask

CORPUS_VERSION = "reaper-item-edits-v1"


def generate_item_edit_chains(count: int = 20, seed: int = 20260924) -> list[CorpusChain]:
    if not 1 <= count <= 1000:
        raise ValueError("chain count must be between 1 and 1000")
    chains = []
    for index in range(count):
        rng = random.Random(seed + index)
        tempo = rng.choice([90, 100, 120, 150])
        start = rng.choice([0.0, 2.0, 4.0])
        cut = rng.choice([0.5, 0.75, 1.0, 1.25, 1.5])
        delay = rng.choice([0.5, 1.0, 1.5, 2.0])
        initial = MusicProject(tempo=tempo, assets=[{
            "id": "tone", "kind": "audio", "name": "Owned source WAV", "duration_seconds": 2.0,
            "provenance": {"source": "procedural_fixture", "license": "benchmark-owned", "rights_verified": True}}],
            tracks=[{"id": "samples", "name": "Samples", "kind": "audio", "clips": [{
                "id": "hit", "kind": "audio", "asset_id": "tone", "timeline_start_beats": start,
                "source_start": 0.0, "source_end": 2.0, "pitch_semitones": 0.0,
                "stretch_ratio": 1.0, "reversed": False,
                "fade_in_seconds": 0.0, "fade_out_seconds": 0.0}]}])
        chain_id = f"item-{index:04d}"
        split = "train" if index % 10 < 6 else "dev" if index % 10 < 8 else "test"
        steps = []
        state = initial
        for family, prompt, ops in [
            ("split", f"At source time {cut} seconds, split audio item 'hit' on 'samples'. "
             "Keep the left item's ID 'hit'; give the right item ID 'tail'. Keep the two pieces adjacent "
             "and preserve their source ranges, playback rate, pitch, gain and all other project state.",
             [operation("split_audio_clip", track_id="samples", clip_id="hit", new_clip_id="tail", source_seconds=cut)]),
            ("move", f"Move only audio item 'tail' on 'samples' to beat "
             f"{round(start + cut * tempo / 60 + delay, 9)}. Leave the left item, both source selections "
             "and every other setting unchanged.",
             [operation("move_audio_clip", track_id="samples", clip_id="tail",
                        timeline_start_beats=round(start + cut * tempo / 60 + delay, 9))])]:
            env = MusicEnvironment(state, [op["tool"] for op in ops])
            for op in ops:
                env.call(op["tool"], **op["arguments"])
            expected = env.project
            evaluators = [{"type": "project_property", "path": key, "equals": value}
                          for key, value in expected.to_dict().items()]
            evaluators.append({"type": "preserve_except", "paths": _diff_paths(state.to_dict(), expected.to_dict())})
            evaluators.append({"type": "render_valid"})
            task = RostrumTask(f"{chain_id}-{len(steps):02d}-{family}", "L2", prompt +
                " Save the native project and render a non-silent WAV.", deepcopy(state),
                ["inspect_project", *[op["tool"] for op in ops], "render", "inspect_render", "analyze_render"],
                evaluators, tags=[CORPUS_VERSION, family, split],
                required_capabilities=["audio_clips", "readback", "offline_render"], execution_level="E2")
            steps.append(CorpusStep(task, ops, expected))
            state = expected
        chains.append(CorpusChain(chain_id, split, steps))
    return chains
