"""Rostrum-DAW-20: five MIDI, five sample, five mix, five feedback tasks."""
from __future__ import annotations
import re
from copy import deepcopy
from .agent import ReferenceAgent
from .models import MusicProject, RostrumTask
from .symbolic_generator import generate_symbolic_task
from .multistep_generator import generate_multistep_task
from .sample_tasks import sample_project


def phrase_project() -> MusicProject:
    return MusicProject(tracks=[{"id": "keys", "name": "Keys", "kind": "midi", "gain_db": 0.0,
        "clips": [{"id": "phrase", "kind": "midi", "start": 0.0, "length": 4.0,
                   "notes": [{"id": f"n{i}", "pitch": p, "start": float(i), "duration": 0.75,
                              "velocity": 90} for i, p in enumerate([60, 64, 67, 72])]}]}])


def generate_daw_suite(seed: int = 20260922) -> list[RostrumTask]:
    tasks = []
    for i in range(5):
        task = generate_symbolic_task(i, seed+i) if i < 4 else generate_multistep_task(1, seed+i)
        task.initial_project.metadata["family"] = "daw-midi"
        # The native portable subset uses REAPER's 960 ticks/quarter resolution.
        for track in task.initial_project.tracks:
            for clip in track.get("clips", []):
                for note in clip.get("notes", []):
                    note["start"] = round(round(note["start"] * 960) / 960, 9)
                    note["duration"] = round(round(note["duration"] * 960) / 960, 9)
        task.id = f"DAW-{i+1:03d}-midi"
        tasks.append(task)
    for i, (tool, prompt, values) in enumerate([
        ("trim_clip", "Trim clip 'hit-1' on track 'samples' to use only source audio from 0.40s through 0.90s.", {"source_start": 0.4, "source_end": 0.9}),
        ("set_clip_pitch", "Pitch clip 'hit-1' on track 'samples' down 12 semitones.", {"pitch_semitones": -12.0}),
        ("stretch_clip", "Time-stretch clip 'hit-1' on track 'samples' to 1.5x its current duration without changing its pitch.", {"stretch_ratio": 1.5}),
        ("trim_clip", "Trim clip 'hit-1' on track 'samples' to use only source audio from 0.10s through 1.20s.", {"source_start": 0.1, "source_end": 1.2}),
        ("set_clip_pitch", "Pitch clip 'hit-1' on track 'samples' up 7 semitones.", {"pitch_semitones": 7.0}),
    ]):
        project = sample_project()
        project.tracks = project.tracks[:1]
        project.metadata["family"] = "daw-sample"
        tasks.append(RostrumTask(f"DAW-{i+6:03d}-sample", "L2", prompt, project, ["inspect_project", tool],
            [{"type": "project_property", "path": f"tracks.0.clips.0.{key}", "equals": value} for key, value in values.items()] +
            [{"type": "preserve_except", "paths": [f"tracks.0.clips.0.{key}" for key in values]}]))
    mixes = [
        ("Set track 'keys' gain to -6 dB.", "set_track_gain", "tracks.0.gain_db", -6.0),
        ("Set track 'keys' pan to -0.5.", "set_track_pan", "tracks.0.pan", -0.5),
        ("Set track 'keys' pan to 0.75.", "set_track_pan", "tracks.0.pan", 0.75),
        ("Add a send from track 'keys' to track 'bus' at -6 dB.", "add_send", "tracks.0.sends", [{"destination_id": "bus", "gain_db": -6.0}]),
        ("Add gain effect 'trim' on track 'keys' at -9 dB.", "add_gain_effect", "tracks.0.effects", [{"id": "trim", "type": "gain", "gain_db": -9.0}]),
    ]
    for i, (prompt, tool, path, value) in enumerate(mixes):
        project = phrase_project()
        project.tracks.append({"id": "bus", "name": "Bus", "kind": "audio"})
        project.metadata["family"] = "daw-mix"
        tasks.append(RostrumTask(f"DAW-{i+11:03d}-mix", "L2", prompt, project, ["inspect_project", tool],
            [{"type": "project_property", "path": path, "equals": value}, {"type": "preserve_except", "paths": [path]}]))
    for i, target in enumerate([-24, -21, -18, -27, -30]):
        project = phrase_project()
        project.tracks[0]["gain_db"] = -12.0 - i
        project.metadata["family"] = "daw-feedback"
        tasks.append(RostrumTask(f"DAW-{i+16:03d}-feedback", "L2",
            f"Render and analyze the phrase, then adjust only track 'keys' gain to achieve RMS {target} dBFS within 0.5 dB. Render again and verify the improvement.",
            project, ["inspect_project", "set_track_gain", "render", "inspect_render", "analyze_render"],
            [{"type": "render_rms_target", "target_dbfs": target, "tolerance_db": 0.5},
             {"type": "feedback_improvement", "target_dbfs": target},
             {"type": "preserve_except", "paths": ["tracks.0.gain_db"]}], execution_level="E3"))
    for task in tasks:
        task.execution_level = task.execution_level or "E2"
        task.required_capabilities = ["readback", "offline_render", "audio_clips" if "sample" in task.id else "midi_notes"]
        task.allowed_tools = list(dict.fromkeys(task.allowed_tools + ["render", "inspect_render", "analyze_render"]))
        task.evaluators.append({"type": "render_valid"})
        if task.initial_project.metadata["family"] == "daw-midi":
            from .benchmark import oracle
            task.evaluators.append({"type": "preserve_except", "paths": oracle(task)["changed_paths"]})
        task.prompt += " Save a final non-silent render of the completed project."
    return tasks


class DawReferenceAgent:
    """Prompt/measurement-driven control; never reads hidden evaluator specifications."""
    def solve(self, task, environment):
        prompt = task.prompt
        project = environment.call("inspect_project")
        match = re.search(r"achieve RMS (-?[\d.]+) dBFS", prompt)
        if match:
            target = float(match.group(1))
            for _ in range(3):
                render = environment.call("render")
                observation = environment.call("analyze_render", render_id=render["render_id"])
                if observation["rms_dbfs"] is None:
                    raise ValueError("cannot correct gain from a silent signal")
                error = target - observation["rms_dbfs"]
                if abs(error) <= 0.5:
                    return
                current = environment.call("inspect_project", path="tracks.0.gain_db")
                environment.call("set_track_gain", track_id="keys", gain_db=round(current + error, 6))
            environment.call("render")
            return
        match = re.search(r"Trim clip '([^']+)' on track '([^']+)'.*from ([\d.]+)s through ([\d.]+)s", prompt)
        if match:
            clip, track, start, end = match.groups()
            environment.call("trim_clip", track_id=track, clip_id=clip, source_start=float(start), source_end=float(end))
        elif match := re.search(r"Pitch clip '([^']+)' on track '([^']+)' (up|down) ([\d.]+) semitones", prompt):
            clip, track, direction, amount = match.groups()
            environment.call("set_clip_pitch", track_id=track, clip_id=clip, semitones=float(amount)*(1 if direction=="up" else -1))
        elif match := re.search(r"Time-stretch clip '([^']+)' on track '([^']+)' to ([\d.]+)x", prompt):
            clip, track, ratio = match.groups()
            environment.call("stretch_clip", track_id=track, clip_id=clip, ratio=float(ratio))
        elif match := re.search(r"Set track '([^']+)' pan to (-?[\d.]+)\.", prompt):
            environment.call("set_track_pan", track_id=match[1], pan=float(match[2]))
        elif match := re.search(r"Add a send from track '([^']+)' to track '([^']+)' at (-?[\d.]+) dB", prompt):
            environment.call("add_send", track_id=match[1], destination_id=match[2], gain_db=float(match[3]))
        elif match := re.search(r"Add gain effect '([^']+)' on track '([^']+)' at (-?[\d.]+) dB", prompt):
            environment.call("add_gain_effect", effect_id=match[1], track_id=match[2], gain_db=float(match[3]))
        else:
            ReferenceAgent().solve(task, environment)
        environment.call("render")
