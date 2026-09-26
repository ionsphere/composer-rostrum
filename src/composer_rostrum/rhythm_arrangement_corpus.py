"""Linked kick-rhythm and guitar-alignment edits in native REAPER projects."""
from __future__ import annotations

from copy import deepcopy
import random

from .corpus import CorpusChain, CorpusStep, operation
from .environment import MusicEnvironment, _diff_paths
from .models import MusicProject, RostrumTask

CORPUS_VERSION = "reaper-rhythm-arrangement-v1"
PATTERNS = (
    (0.0, 1.0, 2.0, 3.0),
    (0.0, 1.5, 2.0, 3.5),
    (0.0, 0.75, 2.0, 2.75),
    (0.0, 1.0, 2.5, 3.25),
)


def generate_rhythm_arrangement_chains(count: int = 20, seed: int = 20260926) -> list[CorpusChain]:
    if not 1 <= count <= 1000:
        raise ValueError("chain count must be between 1 and 1000")
    chains = []
    for index in range(count):
        rng = random.Random(seed + index)
        tempo = rng.choice([90, 100, 120, 150])
        onsets = list(rng.choice(PATTERNS))
        kick_ids = [f"k{i}" for i in range(len(onsets))]
        guitar_ids = [f"g{i}" for i in range(len(onsets))]
        def clips(ids, asset, duration, shift):
            return [{"id": identity, "kind": "audio", "asset_id": asset,
                     "timeline_start_beats": beat + shift,
                     "source_start": 0.0, "source_end": duration,
                     "pitch_semitones": 0.0, "stretch_ratio": 1.0,
                     "reversed": False, "fade_in_seconds": 0.0,
                     "fade_out_seconds": 0.0} for identity, beat in zip(ids, onsets)]
        initial = MusicProject(tempo=tempo, assets=[
            {"id": "kick", "kind": "audio", "name": "Owned synthesized kick",
             "duration_seconds": 0.22, "fixture": "kick",
             "provenance": {"source": "procedural_fixture", "license": "benchmark-owned",
                            "rights_verified": True}},
            {"id": "guitar", "kind": "audio", "name": "Owned plucked-string proxy",
             "duration_seconds": 0.28, "fixture": "guitar",
             "provenance": {"source": "procedural_fixture", "license": "benchmark-owned",
                            "rights_verified": True}}], tracks=[
            {"id": "kick", "name": "Kick", "kind": "audio", "gain_db": -3.0,
             "clips": clips(kick_ids, "kick", 0.22, 0.25)},
            {"id": "guitar", "name": "Guitar", "kind": "audio", "gain_db": -6.0,
             "clips": clips(guitar_ids, "guitar", 0.28, 0.5)}])
        chain_id = f"rhythm-{index:04d}"
        split = "train" if index % 10 < 6 else "dev" if index % 10 < 8 else "test"
        state, steps = initial, []
        for stage, track_id, ids, prompt in (
            ("kick-rhythm", "kick", kick_ids,
             f"Set the kick drum hits to this one-bar rhythm at {tempo} BPM: beats {onsets}. "
             "Move only the kick items; keep their source audio and the guitar track unchanged."),
            ("guitar-alignment", "guitar", guitar_ids,
             "Align each guitar accent exactly with the corresponding kick hit. "
             "Move only the guitar items; keep the kick rhythm and both sources unchanged.")):
            ops = [operation("move_audio_clip", track_id=track_id, clip_id=identity,
                             timeline_start_beats=beat)
                   for identity, beat in zip(ids, onsets)]
            env = MusicEnvironment(state, ["move_audio_clip"])
            for op in ops:
                env.call(op["tool"], **op["arguments"])
            expected = env.project
            evaluators = [{"type": "project_property", "path": key, "equals": value}
                          for key, value in expected.to_dict().items()]
            evaluators += [{"type": "preserve_except",
                            "paths": _diff_paths(state.to_dict(), expected.to_dict())},
                           {"type": "rhythm_pattern", "track_id": track_id,
                            "clip_ids": ids, "onsets_beats": onsets},
                           {"type": "render_valid"}]
            if stage == "guitar-alignment":
                evaluators.append({"type": "track_alignment", "left_track_id": "kick",
                                   "left_clip_ids": kick_ids, "right_track_id": "guitar",
                                   "right_clip_ids": guitar_ids, "offset_beats": 0})
            task = RostrumTask(f"{chain_id}-{len(steps):02d}-{stage}", "L2",
                prompt + " Save the native project and render a non-silent WAV.",
                deepcopy(state), ["inspect_project", "move_audio_clip", "render",
                                  "inspect_render", "analyze_render"], evaluators,
                tags=[CORPUS_VERSION, stage, split],
                required_capabilities=["audio_clips", "readback", "offline_render"],
                execution_level="E2")
            steps.append(CorpusStep(task, ops, expected))
            state = expected
        chains.append(CorpusChain(chain_id, split, steps))
    return chains
