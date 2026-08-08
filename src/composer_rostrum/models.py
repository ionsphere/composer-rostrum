from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MusicProject:
    tempo: float = 120.0
    meter: str = "4/4"
    key: str | None = None
    tracks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MusicProject":
        return cls(
            tempo=float(data.get("tempo", 120)),
            meter=data.get("meter", "4/4"),
            key=data.get("key"),
            tracks=list(data.get("tracks", [])),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tempo": self.tempo,
            "meter": self.meter,
            "key": self.key,
            "tracks": self.tracks,
            "metadata": self.metadata,
        }


@dataclass
class RostrumTask:
    id: str
    level: str
    prompt: str
    initial_project: MusicProject
    allowed_tools: list[str]
    evaluators: list[dict[str, Any]]
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RostrumTask":
        return cls(
            id=data["id"],
            level=data["level"],
            prompt=data["prompt"],
            initial_project=MusicProject.from_dict(data["initial_project"]),
            allowed_tools=list(data.get("allowed_tools", [])),
            evaluators=list(data.get("evaluators", [])),
            tags=list(data.get("tags", [])),
        )


@dataclass
class EvaluationResult:
    evaluator: str
    passed: bool
    score: float
    message: str = ""
