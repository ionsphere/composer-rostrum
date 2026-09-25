"""Seeded, linked creation/revision tasks; targets never belong in agent inputs."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import random

from .environment import _diff_paths
from .models import MusicProject, RostrumTask

CORPUS_VERSION = "reaper-chains-v1"


@dataclass
class CorpusStep:
    task: RostrumTask
    operations: list[dict]
    expected: MusicProject | None


@dataclass
class CorpusChain:
    id: str
    split: str
    steps: list[CorpusStep]


def operation(tool, **arguments):
    return {"tool": tool, "arguments": arguments}


def generate_chains(count: int = 40, seed: int = 20260923) -> list[CorpusChain]:
    """Six stages per independent composition; split assignment never cuts a chain.

    These are procedural reference demonstrations, not model/human performances.
    Final feedback gains are intentionally determined by actual audio measurements.
    """
    if not 1 <= count <= 1000:
        raise ValueError("chain count must be between 1 and 1000")
    chains = []
    for index in range(count):
        rng = random.Random(seed + index)
        chain_id = f"chain-{index:04d}"
        split = "train" if index % 10 < 6 else "dev" if index % 10 < 8 else "test"
        initial = MusicProject(assets=[{"id": "tone", "kind": "audio", "name": "Procedural tone",
            "duration_seconds": 2.0, "provenance": {"source": "procedural_fixture",
                "license": "benchmark-owned", "rights_verified": True}}])
        state = deepcopy(initial)
        steps = []

        def add(family, prompt, expected, operations, evaluators=None):
            nonlocal state
            allowed = list(dict.fromkeys(["inspect_project", *[o["tool"] for o in operations],
                                         "render", "inspect_render", "analyze_render"]))
            if expected is not None:
                specs = [{"type": "project_property", "path": k, "equals": v}
                         for k, v in expected.to_dict().items()]
                specs.append({"type": "preserve_except", "paths": _diff_paths(state.to_dict(), expected.to_dict())})
            else:
                specs = evaluators
            task = RostrumTask(f"{chain_id}-{len(steps):02d}-{family}", "L2", prompt +
                " Preserve everything else. Render the completed project to a non-silent WAV.",
                deepcopy(state), allowed, specs + [{"type": "render_valid"}],
                tags=[CORPUS_VERSION, family, split], required_capabilities=["midi_notes", "audio_clips", "readback", "offline_render"],
                execution_level="E3" if expected is None else "E2")
            steps.append(CorpusStep(task, operations, deepcopy(expected)))
            if expected is not None:
                state = deepcopy(expected)

        tempo = 90 + index % 190  # Musical variation, independent of metadata/IDs.
        root = rng.randrange(48, 65)
        pitches = [root + p for p in rng.choice([[0, 4, 7, 12], [0, 3, 7, 10], [0, 7, 5, 12], [0, 2, 7, 9]])]
        starts = rng.choice([[0, 1, 2, 3], [0, 0.5, 2, 3.5], [0, 1.5, 2.5, 3]])
        notes = [{"id": f"n{i}", "pitch": pitch, "start": starts[i], "duration": 0.375,
                  "velocity": rng.randrange(65, 106)} for i, pitch in enumerate(pitches)]
        desired = deepcopy(state)
        desired.tempo = tempo
        desired.tracks = [
            {"id": "keys", "name": "Keys", "kind": "midi", "gain_db": -6.0, "clips": [
                {"id": "phrase", "kind": "midi", "start": 0.0, "length": 4.0, "notes": notes}]},
            {"id": "samples", "name": "Samples", "kind": "audio", "gain_db": -9.0, "clips": [
                {"id": "hit", "kind": "audio", "asset_id": "tone", "timeline_start_beats": 0.0,
                 "source_start": 0.0, "source_end": 2.0, "pitch_semitones": 0.0, "stretch_ratio": 1.0, "reversed": False}]},
            {"id": "bus", "name": "Bus", "kind": "audio", "gain_db": -6.0, "clips": []}]
        ops = [operation("set_tempo", bpm=tempo)]
        for track in desired.tracks:
            ops.append(operation("add_track", track_id=track["id"], name=track["name"], kind=track["kind"], gain_db=track["gain_db"]))
        ops += [operation("add_midi_clip", track_id="keys", clip_id="phrase", start=0.0, length=4.0, notes=deepcopy(notes)),
                operation("add_audio_clip", track_id="samples", clip_id="hit", asset_id="tone", timeline_start_beats=0.0, source_start=0.0, source_end=2.0)]
        add("create", f"Build a project at {tempo} BPM, keeping 4/4 meter. Add MIDI track 'keys' named 'Keys' at -6 dB, "
            "audio track 'samples' named 'Samples' at -9 dB, and empty audio track 'bus' named 'Bus' at -6 dB, in that order. "
            "On keys add MIDI clip 'phrase' at beat 0 with length 4 beats and these notes (pitch is MIDI number; times are beats): "
            + json.dumps(notes) + ". On samples add audio clip 'hit' from provided asset 'tone', at beat 0 using source seconds 0 through 2, "
            "original pitch and duration, forward playback. Leave bus empty and keep default routing.", desired, ops)

        delta = rng.choice([-7, -5, 3, 5, 7, 12])
        desired = deepcopy(state)
        for note in desired.tracks[0]["clips"][0]["notes"]:
            note["pitch"] += delta
        add("transpose", f"Transpose all notes in 'phrase' on 'keys' by {delta} semitones, keeping note identities, timing and velocities.",
            desired, [operation("transpose_notes", track_id="keys", clip_id="phrase", semitones=delta)])

        start, end = rng.choice([0.1, 0.2, 0.3]), rng.choice([1.2, 1.4, 1.6])
        fade_in, fade_out = rng.choice([0.05, 0.1, 0.15]), rng.choice([0.15, 0.2, 0.25])
        desired = deepcopy(state)
        desired.tracks[1]["clips"][0].update(source_start=start, source_end=end, fade_in_seconds=fade_in, fade_out_seconds=fade_out)
        add("trim-fades", f"Trim 'hit' on 'samples' to source seconds {start} through {end}. Set linear item fades: "
            f"{fade_in} seconds in and {fade_out} seconds out. Keep its timeline position.", desired,
            [operation("trim_clip", track_id="samples", clip_id="hit", source_start=start, source_end=end),
             operation("set_clip_fades", track_id="samples", clip_id="hit", fade_in_seconds=fade_in, fade_out_seconds=fade_out)])

        pitch, ratio = rng.choice([-12, -5, 7, 12]), rng.choice([0.75, 1.25, 1.5])
        desired = deepcopy(state)
        desired.tracks[1]["clips"][0].update(pitch_semitones=float(pitch), stretch_ratio=ratio)
        add("pitch-stretch", f"Set 'hit' on 'samples' to {pitch} semitones relative to its original source and stretch ratio {ratio} "
            "relative to its source selection. Preserve its fades in seconds and use pitch-preserving time stretch.", desired,
            [operation("set_clip_pitch", track_id="samples", clip_id="hit", semitones=pitch),
             operation("stretch_clip", track_id="samples", clip_id="hit", ratio=ratio)])

        pan, gain, send = rng.choice([-0.75, -0.5, 0.5, 0.75]), rng.choice([-3, -6, -9]), rng.choice([-6, -9, -12])
        desired = deepcopy(state)
        desired.tracks[0].update(pan=pan, sends=[{"destination_id": "bus", "gain_db": float(send)}])
        desired.tracks[1]["effects"] = [{"id": "trim", "type": "gain", "gain_db": float(gain)}]
        add("mix", f"Pan 'keys' to {pan}. Add audio send keys → bus at {send} dB and gain effect 'trim' on 'samples' at {gain} dB. "
            "Keep both source tracks' direct master output enabled.", desired,
            [operation("set_track_pan", track_id="keys", pan=pan), operation("add_send", track_id="keys", destination_id="bus", gain_db=send),
             operation("add_gain_effect", track_id="samples", effect_id="trim", gain_db=gain)])

        target = rng.choice([-30, -27, -24])
        add("feedback", f"Render and analyze this mix, then adjust only 'keys' and 'samples' track gains to achieve RMS {target} dBFS "
            "within 0.5 dB. Render again and verify that the RMS error improved.", None,
            [operation("set_track_gain", track_id="keys", gain_db=0)],
            [{"type": "preserve_except", "paths": ["tracks.0.gain_db", "tracks.1.gain_db"]},
             {"type": "render_rms_target", "target_dbfs": target, "tolerance_db": 0.5},
             {"type": "feedback_improvement", "target_dbfs": target}])
        # No scripted target gain is supplied for measurement-driven feedback.
        steps[-1].operations = []
        chains.append(CorpusChain(chain_id, split, steps))
    return chains
