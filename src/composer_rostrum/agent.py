from __future__ import annotations

import re
from typing import Protocol

from .environment import MusicEnvironment
from .models import RostrumTask


class Agent(Protocol):
    def solve(self, task: RostrumTask, environment: MusicEnvironment) -> None:
        """Use only the environment tool surface to solve the task."""
        ...


class ReferenceAgent:
    """Deterministic baseline used to validate benchmark plumbing.

    It reads the natural-language request, never evaluator specifications.
    """

    def solve(self, task: RostrumTask, environment: MusicEnvironment) -> None:
        environment.call("inspect_project")
        prompt = task.prompt

        if "set_tempo" in environment.allowed_tools:
            match = re.search(r"tempo to ([0-9]+(?:\.[0-9]+)?) BPM", prompt, re.I)
            if match:
                environment.call("set_tempo", bpm=float(match.group(1)))
                return

        if "set_key" in environment.allowed_tools:
            match = re.search(r"key to ([A-G](?:#|b)?_(?:major|minor))", prompt, re.I)
            if match:
                environment.call("set_key", key=match.group(1))
                return

        if "set_meter" in environment.allowed_tools:
            match = re.search(r"meter to ([0-9]+/[0-9]+)", prompt, re.I)
            if match:
                environment.call("set_meter", meter=match.group(1))
                return

        if "mute_track" in environment.allowed_tools:
            match = re.search(r"Mute track '([^']+)'", prompt, re.I)
            if match:
                environment.call("mute_track", track_id=match.group(1), muted=True)
                return

        if "set_track_gain" in environment.allowed_tools:
            match = re.search(r"Set track '([^']+)' gain to (-?[0-9]+(?:\.[0-9]+)?) dB", prompt, re.I)
            if match:
                environment.call("set_track_gain", track_id=match.group(1), gain_db=float(match.group(2)))
                return
