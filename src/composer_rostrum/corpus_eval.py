"""Evaluate an agent from a captured native input, with targets outside its tools."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import time

from .backends.base import BackendError
from .backends.reaper import ReaperBackend
from .corpus_capture import moved_item_pcm_matches, pcm_equivalent, sha256, write_json
from .ear import compare as compare_audio, judge as judge_audio, evaluate_production
from .environment import project_hash
from .evaluator import evaluate
from .models import EvaluationResult, MusicProject, RostrumTask
from .render_evaluator import evaluate_renders


def dataset_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("corpus path escapes dataset")
    return path


def load_sample(dataset: Path, sample_id: str):
    """Integrity-check every consumed input/target file against the frozen inventory."""
    dataset = dataset.resolve()
    inventory = json.loads((dataset / "checksums.json").read_text(encoding="utf-8"))

    def read(relative):
        path = dataset_path(dataset, relative)
        if inventory.get(relative) != sha256(path):
            raise ValueError(f"corpus checksum mismatch: {relative}")
        return path

    rows = [json.loads(line) for line in read("samples.jsonl").read_text(encoding="utf-8").splitlines()]
    matches = [row for row in rows if row["id"] == sample_id]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one sample matching {sample_id!r}")
    row = matches[0]
    public = json.loads(read(row["input"]).read_text(encoding="utf-8"))
    private = json.loads(read(row["private_target"]).read_text(encoding="utf-8"))
    task = RostrumTask.from_dict(private["task"])
    if task.id != public["id"] or task.prompt != public["prompt"] or task.allowed_tools != public["allowed_tools"]:
        raise ValueError("public task differs from private scoring specification")
    state = public["input_state"]
    manifest = json.loads(read(state + "/state.json").read_text(encoding="utf-8"))
    for relative, digest in manifest["files"].items():
        path = read(state + "/" + relative)
        if sha256(path) != digest:
            raise ValueError("state and dataset checksums disagree")
    initial = MusicProject.from_dict(json.loads(read(state + "/project.music-ir.json").read_text(encoding="utf-8")))
    if project_hash(initial) != project_hash(task.initial_project) or project_hash(initial) != manifest["project_hash"]:
        raise ValueError("native input manifest differs from task initial state")
    return task, public, dataset_path(dataset, state)


def evaluate_item_audio(task, before, after, input_render: Path, renders):
    """Score the audible relationship, independent of native property readback."""
    if "reaper-item-edits-v1" not in task.tags:
        return []
    valid = False
    if input_render.is_file() and renders and not renders[-1].metrics["silent"]:
        try:
            output_render = renders[-1].path
            if "split" in task.tags:
                valid = pcm_equivalent(input_render, output_render, 1)
            elif "move" in task.tags:
                source = before.tracks[0]["clips"][0]
                left, right = after.tracks[0]["clips"]
                valid = moved_item_pcm_matches(input_render, output_render, before.tempo,
                    source["timeline_start_beats"], left["source_end"], right["timeline_start_beats"])
        except (IndexError, KeyError, OSError, ValueError):
            valid = False
    return [EvaluationResult("item_audio_relation", valid, float(valid),
        "audio matches item edit" if valid else "rendered waveform does not match item edit")]


def reference_audio_path(dataset: Path, sample_id: str) -> Path:
    """Keep target audio on the evaluator side and verify its frozen checksum."""
    dataset = dataset.resolve()
    inventory = json.loads((dataset / "checksums.json").read_text(encoding="utf-8"))
    index = dataset / "samples.jsonl"
    if inventory.get("samples.jsonl") != sha256(index):
        raise ValueError("corpus index checksum mismatch")
    matches = [row for row in (json.loads(line) for line in index.read_text(encoding="utf-8").splitlines())
               if row["id"] == sample_id]
    if len(matches) != 1:
        raise ValueError("expected exactly one reference sample")
    private_relative = matches[0]["private_target"]
    private_file = dataset_path(dataset, private_relative)
    if inventory.get(private_relative) != sha256(private_file):
        raise ValueError("private scoring specification checksum mismatch")
    private = json.loads(private_file.read_text(encoding="utf-8"))
    relative = private["target_state"] + "/render.wav"
    target = dataset_path(dataset, relative)
    if inventory.get(relative) != sha256(target):
        raise ValueError("target audio checksum mismatch")
    return target


def production_audio_expectation(dataset: Path, sample_id: str) -> dict:
    """Read the checksum-verified private region oracle for a production sample."""
    dataset = dataset.resolve()
    inventory = json.loads((dataset / "checksums.json").read_text(encoding="utf-8"))
    index = dataset / "samples.jsonl"
    if inventory.get("samples.jsonl") != sha256(index):
        raise ValueError("corpus index checksum mismatch")
    matches = [row for row in (json.loads(line) for line in index.read_text(encoding="utf-8").splitlines())
               if row["id"] == sample_id]
    if len(matches) != 1:
        raise ValueError("expected exactly one production sample")
    private_relative = matches[0]["private_target"]
    private_file = dataset_path(dataset, private_relative)
    if inventory.get(private_relative) != sha256(private_file):
        raise ValueError("private scoring specification checksum mismatch")
    return json.loads(private_file.read_text(encoding="utf-8"))["audio_expectation"]


def run_sample(dataset: Path, sample_id: str, agent, executable: str, output: Path):
    task, public, state = load_sample(dataset, sample_id)
    target_audio = (reference_audio_path(dataset, sample_id) if task.execution_level == "E2" and
                    any(tag in task.tags for tag in ("reaper-chains-v1", "reaper-item-edits-v1",
                                                       "reaper-clip-gain-v1",
                                                       "reaper-rhythm-arrangement-v1")) else None)
    production_expectation = (production_audio_expectation(dataset, sample_id)
                              if "reaper-clip-gain-v1" in task.tags else None)
    output.mkdir(parents=True, exist_ok=False)
    backend = ReaperBackend(executable, timeout=60)
    native = backend.materialize(task.initial_project, output)
    shutil.copyfile(state / "project.rpp", native.project_path)
    if (state / "assets").exists():
        shutil.copytree(state / "assets", output / "assets")
    # The evaluation workspace has only input material: no target states, oracle,
    # reference trace, or private task specification is staged for the worker.
    write_json(output / "input.json", public)
    session = environment = None
    result = {"task_id": task.id, "split": public["split"], "passed": False,
              "infrastructure": {"ok": True}, "results": [], "trajectory": [], "renders": []}
    started = time.monotonic()
    try:
        session = backend.open(native, resume=True)
        before = backend.readback(session)
        if project_hash(before) != project_hash(task.initial_project):
            raise BackendError("captured native input does not match declared initial state")
        environment = backend.create_environment(session, task.allowed_tools)
        public_task = deepcopy(task)
        public_task.evaluators = []
        agent.solve(public_task, environment)
        backend.commit_environment(session, environment)
        backend.save(session)
        after = backend.readback(session)
        checks = (evaluate(task, before, after) +
                  evaluate_renders(task, session.state["renders"], environment.trajectory, after) +
                  evaluate_item_audio(task, before, after, state / "render.wav", session.state["renders"]))
        if production_expectation is not None:
            production_passed = False
            if session.state["renders"]:
                try:
                    production = evaluate_production(state / "render.wav", session.state["renders"][-1].path,
                                                     production_expectation)
                    write_json(output / "production-audio-comparison.json", production)
                    production_passed = production["passed"]
                    production_message = f"clip gain checks: {production['checks']}"
                except (OSError, ValueError) as exc:
                    production_message = f"clip gain comparison failed: {exc}"
            else:
                production_message = "no candidate render"
            checks.append(EvaluationResult("production_audio_relation", production_passed,
                                           float(production_passed), production_message))
        if target_audio is not None:
            matching = False
            if session.state["renders"]:
                try:
                    audio_report = compare_audio(target_audio, session.state["renders"][-1].path)
                    verdict = judge_audio(audio_report, {"kind": "same", "min_snr_db": 70})
                    write_json(output / "audio-comparison.json", {**audio_report, "verdict": verdict})
                    matching = verdict["passed"]
                    message = (f"reference waveform SNR {audio_report['difference']['waveform_snr_db']} dB; "
                               f"duration difference {audio_report['difference']['duration_ms']} ms")
                except (OSError, ValueError) as exc:
                    message = f"reference audio comparison failed: {exc}"
            else:
                message = "no candidate render"
            checks.append(EvaluationResult("reference_audio_match", matching, float(matching), message))
        result.update(passed=bool(checks) and all(c.passed for c in checks), results=[asdict(c) for c in checks],
                      project=after.to_dict(), project_hash=project_hash(after))
        if not result["passed"]:
            result["failure_class"] = "evaluation"
    except BackendError as exc:
        result.update(failure_class="infrastructure", infrastructure={"ok": False, "error": str(exc)})
    except Exception as exc:
        result.update(failure_class="agent_error", error=f"{type(exc).__name__}: {exc}")
    finally:
        if environment is not None:
            result["trajectory"] = [e.to_dict() for e in environment.trajectory]
        if session is not None:
            result["renders"] = [r.to_dict() for r in session.state["renders"]]
            backend.close(session)
        if hasattr(agent, "usage"):
            result["model_usage"] = deepcopy(agent.usage)
        if hasattr(agent, "responses"):
            result["model_responses"] = deepcopy(agent.responses)
        result["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "outcome.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("sample_id")
    parser.add_argument("--reaper", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort", choices=["low", "medium", "high"])
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--max-tool-calls", type=int, default=50)
    args = parser.parse_args()
    from .model_agent import ResponsesAgent
    agent = ResponsesAgent(args.model, args.reasoning_effort, args.max_turns, args.max_tool_calls)
    result = run_sample(args.dataset, args.sample_id, agent, args.reaper, args.output)
    print(json.dumps({k: result[k] for k in ("task_id", "passed", "infrastructure", "elapsed_seconds")}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
