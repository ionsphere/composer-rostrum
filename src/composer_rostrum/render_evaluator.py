"""Audio and causal feedback checks, run outside the agent observation boundary."""
from __future__ import annotations
from .environment import project_hash
from .models import EvaluationResult

RENDER_EVALUATORS = {"render_valid", "render_rms_target", "feedback_improvement"}


def evaluate_renders(task, renders, trajectory, after):
    results = []
    for spec in task.evaluators:
        kind = spec["type"]
        if kind not in RENDER_EVALUATORS:
            continue
        last = renders[-1] if renders else None
        valid = bool(last and last.project_hash == project_hash(after) and not last.metrics["silent"])
        passed = valid
        if kind == "render_rms_target":
            passed = valid and last.metrics["rms_dbfs"] is not None and abs(last.metrics["rms_dbfs"] - spec["target_dbfs"]) <= spec.get("tolerance_db", 0.5)
        if kind == "feedback_improvement":
            passed = valid and len(renders) >= 2
            if passed:
                first = renders[0]
                initial, final = first.metrics["rms_dbfs"], last.metrics["rms_dbfs"]
                target = spec["target_dbfs"]
                observed = [e.index for e in trajectory if e.tool == "analyze_render" and not e.error
                            and e.arguments.get("render_id") == first.render_id]
                edits = [e.index for e in trajectory if e.before_hash != e.after_hash and not e.error]
                final_events = [e.index for e in trajectory if e.tool == "render" and not e.error
                                and e.result and e.result.get("render_id") == last.render_id]
                passed = bool(initial is not None and final is not None and
                    abs(final-target) < abs(initial-target) and
                    any(o < e < r for o in observed for e in edits for r in final_events))
        results.append(EvaluationResult(kind, bool(passed), float(bool(passed)),
                       "render requirement satisfied" if passed else "missing, stale, silent, or non-improving render"))
    return results
