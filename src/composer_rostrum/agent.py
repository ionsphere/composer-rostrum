from __future__ import annotations

from typing import Protocol

from .models import MusicProject, RostrumTask


class Agent(Protocol):
    """Minimal agent contract used by the benchmark runner."""

    def solve(self, task: RostrumTask, project: MusicProject) -> MusicProject:
        """Return the modified project proposed as the task solution."""
        ...


class ReferenceAgent:
    """Tiny deterministic agent for validating benchmark plumbing.

    It intentionally understands only the initial scaffold's set_tempo tool.
    Real model adapters should live behind the same Agent protocol.
    """

    def solve(self, task: RostrumTask, project: MusicProject) -> MusicProject:
        for evaluator in task.evaluators:
            if evaluator.get("type") == "project_property" and evaluator.get("path") == "tempo":
                project.tempo = float(evaluator["equals"])
        return project
