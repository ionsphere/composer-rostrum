from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import EvaluationResult, MusicProject, RostrumTask


def _read_path(project: MusicProject, path: str) -> Any:
    value: Any = project.to_dict()
    for part in path.split("."):
        if isinstance(value, dict):
            value = value[part]
        elif isinstance(value, list):
            value = value[int(part)]
        else:
            value = getattr(value, part)
    return value


def evaluate(task: RostrumTask, before: MusicProject, after: MusicProject) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []

    for spec in task.evaluators:
        evaluator_type = spec["type"]

        if evaluator_type == "project_property":
            actual = _read_path(after, spec["path"])
            expected = spec["equals"]
            passed = actual == expected
            results.append(EvaluationResult(
                evaluator=f"project_property:{spec['path']}",
                passed=passed,
                score=1.0 if passed else 0.0,
                message=f"expected {expected!r}, got {actual!r}",
            ))
            continue

        if evaluator_type == "preserve_paths":
            changed = []
            for path in spec["paths"]:
                if _read_path(before, path) != _read_path(after, path):
                    changed.append(path)
            passed = not changed
            results.append(EvaluationResult(
                evaluator="preserve_paths",
                passed=passed,
                score=1.0 if passed else 0.0,
                message="preserved" if passed else f"unexpected changes: {', '.join(changed)}",
            ))
            continue

        results.append(EvaluationResult(
            evaluator=evaluator_type,
            passed=False,
            score=0.0,
            message="evaluator type is not implemented yet",
        ))

    return results


def aggregate_score(results: list[EvaluationResult]) -> float:
    if not results:
        return 0.0
    return sum(result.score for result in results) / len(results)
