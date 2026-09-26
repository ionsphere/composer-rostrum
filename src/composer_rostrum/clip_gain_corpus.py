"""Linked REAPER item-gain revisions with preserved mixer state."""
from __future__ import annotations

from copy import deepcopy
import random

from .corpus import CorpusChain, CorpusStep, operation
from .environment import MusicEnvironment, _diff_paths
from .models import MusicProject, RostrumTask

CORPUS_VERSION = "reaper-clip-gain-v1"


def generate_clip_gain_chains(count: int = 20, seed: int = 20260925) -> list[CorpusChain]:
    if not 1 <= count <= 1000:
        raise ValueError("chain count must be between 1 and 1000")
    chains = []
    for index in range(count):
        rng = random.Random(seed + index)
        tempo = rng.choice([90, 100, 120, 150])
        duration = rng.choice([0.4, 0.5, 0.6, 0.8])
        quiet = rng.choice([-12, -9, -6])
        loud = rng.choice([3, 6])
        clips = []
        for clip_id, position, gain in (("quiet", 0.0, quiet),
                                        ("loud", duration * tempo / 60, loud)):
            clips.append({"id": clip_id, "kind": "audio", "asset_id": "tone",
                          "timeline_start_beats": round(position, 9),
                          "source_start": 0.0, "source_end": duration,
                          "pitch_semitones": 0.0, "stretch_ratio": 1.0,
                          "reversed": False, "fade_in_seconds": 0.0,
                          "fade_out_seconds": 0.0, "gain_db": float(gain)})
        initial = MusicProject(tempo=tempo, assets=[{
            "id": "tone", "kind": "audio", "name": "Owned tone",
            "duration_seconds": 2.0,
            "provenance": {"source": "procedural_fixture", "license": "benchmark-owned",
                           "rights_verified": True}}], tracks=[{
            "id": "samples", "name": "Samples", "kind": "audio", "gain_db": 0.0,
            "effects": [], "clips": clips}])
        chain_id = f"gain-{index:04d}"
        split = "train" if index % 10 < 6 else "dev" if index % 10 < 8 else "test"
        state, steps = initial, []
        for clip_id, prompt in (("quiet", "Set the quiet audio item's own gain to 0 dB. "
                                  "Leave the loud item and the track fader unchanged."),
                                ("loud", "Now set the loud item's own gain to 0 dB so the two "
                                 "items have equal level. Leave the quiet item, track fader, "
                                 "and effects unchanged.")):
            ops = [operation("set_clip_gain", track_id="samples", clip_id=clip_id, gain_db=0.0)]
            env = MusicEnvironment(state, ["set_clip_gain"])
            for op in ops:
                env.call(op["tool"], **op["arguments"])
            expected = env.project
            evaluators = [{"type": "project_property", "path": key, "equals": value}
                          for key, value in expected.to_dict().items()]
            evaluators += [{"type": "preserve_except",
                            "paths": _diff_paths(state.to_dict(), expected.to_dict())},
                           {"type": "render_valid"}]
            task = RostrumTask(f"{chain_id}-{len(steps):02d}-{clip_id}", "L2",
                prompt + " Save the REAPER project and render a non-silent WAV.",
                deepcopy(state), ["inspect_project", "set_clip_gain", "render",
                                  "inspect_render", "analyze_render"], evaluators,
                tags=[CORPUS_VERSION, clip_id, split],
                required_capabilities=["audio_clips", "readback", "offline_render"],
                execution_level="E2")
            steps.append(CorpusStep(task, ops, expected))
            state = expected
        chains.append(CorpusChain(chain_id, split, steps))
    return chains
