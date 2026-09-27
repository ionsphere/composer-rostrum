"""Linked native instrument assignment, replacement, and original MIDI riff tasks."""
from __future__ import annotations

from copy import deepcopy
import random

from .corpus import CorpusChain, CorpusStep, operation
from .environment import MusicEnvironment, _diff_paths
from .models import MusicProject, RostrumTask

CORPUS_VERSION = "reaper-instrument-riff-v1"
PITCH_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def pitch_name(pitch: int) -> str:
    return f"{PITCH_NAMES[pitch % 12]}{pitch // 12 - 1}"


def notes(pitches, onsets, duration, prefix, velocity=94):
    return [{"id": f"{prefix}{i}", "pitch": pitch, "velocity": velocity,
             "start": onset, "duration": duration} for i, (pitch, onset) in enumerate(zip(pitches, onsets))]


def generate_instrument_riff_chains(count: int = 20, seed: int = 20260926) -> list[CorpusChain]:
    if not 1 <= count <= 1000:
        raise ValueError("chain count must be between 1 and 1000")
    chains = []
    for index in range(count):
        rng = random.Random(seed + index)
        tempo = rng.choice((96, 108, 120, 132))
        shift = rng.choice((-2, 0, 2, 3))
        roots = [40 + shift, 43 + shift, 48 + shift, 50 + shift] * 2
        onsets = [0, 1.5, 2, 3.5, 4, 5.5, 6, 7.5]
        bass_riff = notes(roots, onsets, 0.5, "b", 100)
        guitar_riff = notes([p + delta for p in roots for delta in (12, 19)],
                            [beat for beat in onsets for _ in (0, 1)], 0.5, "g", 88)
        initial = MusicProject(tempo=tempo, tracks=[{
            "id": "bass", "name": "Bass", "kind": "midi", "gain_db": -6.0,
            "clips": [{"id": "intro", "kind": "midi", "start": 0.0, "length": 2.0,
                       "notes": notes([40 + shift, 43 + shift], [0.0, 1.0], 0.5, "i")}] }])
        intro_guitar = notes([52 + shift, 59 + shift], [0.0, 1.0], 0.5, "i", 85)
        chain_id = f"instrument-{index:04d}"
        split = "train" if index % 10 < 6 else "dev" if index % 10 < 8 else "test"
        state, steps = initial, []
        stages = [
            ("add-a", [operation("add_instrument", track_id="bass", instrument_id="voice-a", patch="bass")],
             "Give the existing Bass MIDI track a bass instrument with ID voice-a. "
             "Keep its two intro notes and everything else unchanged."),
            ("add-b", [operation("add_track", track_id="lead", name="Lead", kind="midi", gain_db=-9.0),
                       operation("add_instrument", track_id="lead", instrument_id="voice-b", patch="organ"),
                       operation("add_midi_clip", track_id="lead", clip_id="intro", start=0.0,
                                 length=2.0, notes=intro_guitar)],
             f"Add a second MIDI instrument track named Lead (ID lead, gain -9 dB), with an organ "
             f"voice (ID voice-b). In a two-beat MIDI clip with ID intro, put {pitch_name(52+shift)} "
             f"at beat 0 and {pitch_name(59+shift)} at beat 1; each note lasts half a beat "
             "with velocity 85. "
             "Keep the Bass track and its bass instrument unchanged."),
            ("swap-b", [operation("set_instrument_patch", track_id="lead", instrument_id="voice-b", patch="guitar")],
             "Change only the Lead instrument from organ to guitar. Preserve its MIDI notes, clip timing, track level, "
             "and the Bass track. The sound should change without re-recording or sampling."),
            ("original-riff", [operation("add_midi_clip", track_id="bass", clip_id="riff", start=4.0,
                                          length=8.0, notes=bass_riff),
                               operation("add_midi_clip", track_id="lead", clip_id="riff", start=4.0,
                                         length=8.0, notes=guitar_riff)],
             "Compose this original two-bar syncopated riff using MIDI notes only; do not import or sample audio. "
             f"At {tempo} BPM, begin at project beat 4. In each bar strike at local beats 0, 1.5, 2, and 3.5; "
             f"repeat the bar once. The bass roots are {', '.join(pitch_name(p) for p in roots[:4])}, "
             "repeated in bar two. On Lead, place a power fifth above each bass root: the root one octave "
             "higher plus its perfect fifth. Each note lasts half a beat; use velocity 100 on Bass and 88 "
             "on Lead. Put each part in an eight-beat MIDI clip with ID riff. Keep the existing intro and instruments."),
        ]
        for stage, ops, prompt in stages:
            env = MusicEnvironment(state, [op["tool"] for op in ops])
            for op in ops:
                env.call(op["tool"], **op["arguments"])
            expected = env.project
            evaluators = [{"type": "project_property", "path": key, "equals": value}
                          for key, value in expected.to_dict().items()
                          if key != "tracks" or stage in ("add-a", "swap-b")]
            if stage == "add-b":
                for path in ("tracks.1.id", "tracks.1.name", "tracks.1.kind", "tracks.1.gain_db",
                             "tracks.1.instruments", "tracks.1.clips.0.id", "tracks.1.clips.0.kind",
                             "tracks.1.clips.0.start", "tracks.1.clips.0.length"):
                    value = expected.to_dict()
                    for part in path.split("."):
                        value = value[int(part)] if isinstance(value, list) else value[part]
                    evaluators.append({"type": "project_property", "path": path, "equals": value})
                evaluators.append({"type": "midi_note_pattern", "track_id": "lead", "clip_id": "intro",
                                   "notes": [[n[k] for k in ("pitch", "start", "duration", "velocity")]
                                             for n in intro_guitar]})
            if stage == "original-riff":
                for track_index in (0, 1):
                    clip = expected.tracks[track_index]["clips"][1]
                    for field in ("id", "kind", "start", "length"):
                        evaluators.append({"type": "project_property",
                                           "path": f"tracks.{track_index}.clips.1.{field}",
                                           "equals": clip[field]})
            evaluators.extend(({"type": "preserve_except",
                                "paths": _diff_paths(state.to_dict(), expected.to_dict())},
                               {"type": "render_valid"}))
            if stage != "original-riff":
                track_id, instrument_id, patch = ("bass", "voice-a", "bass") if stage == "add-a" else (
                    "lead", "voice-b", "organ" if stage == "add-b" else "guitar")
                evaluators.append({"type": "instrument_patch", "track_id": track_id,
                                   "instrument_id": instrument_id, "patch": patch})
            else:
                for track_id, riff in (("bass", bass_riff), ("lead", guitar_riff)):
                    evaluators.append({"type": "midi_note_pattern", "track_id": track_id,
                                       "clip_id": "riff", "notes": [[n[k] for k in ("pitch", "start", "duration", "velocity")]
                                                                 for n in riff]})
            allowed = ["inspect_project", "add_track", "add_instrument", "set_instrument_patch",
                       "add_midi_clip", "render", "inspect_render", "analyze_render"]
            task = RostrumTask(f"{chain_id}-{len(steps):02d}-{stage}", "L2",
                prompt + " Save the native REAPER project and render a non-silent WAV.",
                deepcopy(state), allowed, evaluators, tags=[CORPUS_VERSION, stage, split],
                required_capabilities=["midi_notes", "native_synth", "readback", "offline_render"],
                execution_level="E2")
            steps.append(CorpusStep(task, ops, expected))
            state = expected
        chains.append(CorpusChain(chain_id, split, steps))
    return chains
