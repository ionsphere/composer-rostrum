"""Capture portable native states, private targets, and public per-sample inputs."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

from .backends.base import RenderRequest
from .backends.reaper import ReaperBackend
from .corpus import CORPUS_VERSION, generate_chains
from .environment import project_hash
from .evaluator import evaluate
from .models import MusicProject
from .render_evaluator import evaluate_renders


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(backend, session, destination: Path, render=None):
    """Copy a REAPER-saved file, changing only this worker's absolute path prefix.

    Native musical chunks are never fabricated. Relocated reopen/render verification
    is required separately; hashes alone do not establish native portability.
    """
    destination.mkdir(parents=True, exist_ok=False)
    native = backend.save(session)
    project = backend.readback(session)
    source = native.workspace.resolve()
    text = native.project_path.read_text(encoding="utf-8")
    roots = {source.as_posix(), native.workspace.as_posix()}
    roots |= {root.removeprefix("//?/") for root in roots}
    roots |= {"//?/" + root for root in roots if not root.startswith("//?/")}
    for prefix in sorted({root + "/" for root in roots} | {root.replace("/", "\\") + "\\" for root in roots}, key=len, reverse=True):
        text = text.replace(prefix, "")
    if source.as_posix().lower() in text.lower() or str(source).lower() in text.lower():
        raise ValueError("snapshot still contains a worker path")
    (destination / "project.rpp").write_text(text, encoding="utf-8", newline="\n")
    write_json(destination / "project.music-ir.json", project.to_dict())
    if (source / "assets").exists():
        shutil.copytree(source / "assets", destination / "assets")
    record = {"project_hash": project_hash(project), "native_ids": backend._request(session, "native_ids")}
    if render:
        shutil.copyfile(render.path, destination / "render.wav")
        record["render"] = {"request": render.request.to_dict(), "metrics": render.metrics}
    record["files"] = {p.relative_to(destination).as_posix(): sha256(p) for p in sorted(destination.rglob("*")) if p.is_file()}
    write_json(destination / "state.json", record)
    return record


def verify_snapshot(snapshot_path: Path, workspace: Path, executable: str):
    """Reopen a moved .rpp, without rematerializing its target, and compare PCM."""
    record = json.loads((snapshot_path / "state.json").read_text(encoding="utf-8"))
    for relative, digest in record["files"].items():
        target = (snapshot_path / relative).resolve()
        if not target.is_relative_to(snapshot_path.resolve()) or sha256(target) != digest:
            raise ValueError(f"snapshot checksum mismatch: {relative}")
    project = MusicProject.from_dict(json.loads((snapshot_path / "project.music-ir.json").read_text(encoding="utf-8")))
    backend = ReaperBackend(executable, timeout=60)
    native = backend.materialize(project, workspace)
    shutil.copyfile(snapshot_path / "project.rpp", native.project_path)
    if (snapshot_path / "assets").exists():
        shutil.copytree(snapshot_path / "assets", workspace / "assets")
    session = backend.open(native, resume=True)
    try:
        if project_hash(backend.readback(session)) != record["project_hash"]:
            raise ValueError("relocated snapshot has different native state")
        if backend._request(session, "native_ids") != record["native_ids"]:
            raise ValueError("relocation changed native GUIDs")
        result = {"readback": True, "native_ids": True, "pcm_equal": None}
        if "render" in record:
            actual = backend.render(session, RenderRequest(**record["render"]["request"]))
            result["pcm_equal"] = actual.metrics["pcm_hash"] == record["render"]["metrics"]["pcm_hash"]
            if not result["pcm_equal"]:
                raise ValueError("relocated snapshot PCM differs")
        return result
    finally:
        backend.close(session)


def _stable_ids(before, after):
    return all(identity in after and entry["guid"] == after[identity]["guid"] and
               all(after[identity]["items"].get(cid) == guid for cid, guid in entry["items"].items())
               for identity, entry in before.items())


def _reference(step, environment):
    environment.call("inspect_project")
    if step.expected is not None:
        for op in step.operations:
            environment.call(op["tool"], **op["arguments"])
        environment.call("render")
        return
    target = float(re.search(r"RMS (-?[\d.]+) dBFS", step.task.prompt)[1])
    for attempt in range(4):
        render = environment.call("render")
        metrics = environment.call("analyze_render", render_id=render["render_id"])
        if metrics["rms_dbfs"] is None:
            raise ValueError("silent feedback input")
        error = target - metrics["rms_dbfs"]
        if attempt and abs(error) <= 0.5:
            return
        # All audible source tracks scale equally, including their sends.
        project = environment.call("inspect_project")
        for track in project["tracks"][:2]:
            environment.call("set_track_gain", track_id=track["id"], gain_db=round(track["gain_db"] + error, 6))
    raise ValueError("reference feedback did not converge")


def _cached_chain(dataset, chain):
    """Recover only complete, hash-checked chains matching the requested generator."""
    rows, evidence = [], []
    source_path = None
    for step in chain.steps:
        private_path = Path("private") / f"{step.task.id}.json"
        public_path = Path("inputs") / f"{step.task.id}.json"
        if not (dataset / private_path).is_file() or not (dataset / public_path).is_file():
            return None
        private = json.loads((dataset / private_path).read_text(encoding="utf-8"))
        public = json.loads((dataset / public_path).read_text(encoding="utf-8"))
        if private["task"] != step.task.to_dict() or public["prompt"] != step.task.prompt:
            raise ValueError("existing corpus uses different task specifications; use a new output")
        if not private["results"] or not all(c["passed"] for c in private["results"]):
            return None
        if source_path is not None and public["input_state"] != source_path:
            raise ValueError("broken cached chain linkage")
        for folder in (public["input_state"], private["target_state"]):
            state_path = (dataset / folder).resolve()
            if not state_path.is_relative_to(dataset.resolve()):
                raise ValueError("state escapes dataset")
            record = json.loads((state_path / "state.json").read_text(encoding="utf-8"))
            for relative, digest in record["files"].items():
                file_path = (state_path / relative).resolve()
                if not file_path.is_relative_to(state_path) or sha256(file_path) != digest:
                    raise ValueError("cached state checksum mismatch")
            project = MusicProject.from_dict(json.loads((state_path / "project.music-ir.json").read_text(encoding="utf-8")))
            if project_hash(project) != record["project_hash"]:
                raise ValueError("cached state IR hash mismatch")
            if folder == public["input_state"]:
                if project_hash(project) != project_hash(step.task.initial_project):
                    raise ValueError("cached task input mismatch")
            elif not all(r.passed for r in evaluate(step.task, step.task.initial_project, project)):
                raise ValueError("cached target fails semantic evaluation")
        rows.append({"id": step.task.id, "chain_id": chain.id, "split": chain.split, "stage": step.task.tags[1],
                     "input": public_path.as_posix(), "private_target": private_path.as_posix()})
        evidence.append({"id": step.task.id, "passed": True, "project_hash": record["project_hash"],
                         "pcm_hash": record["render"]["metrics"]["pcm_hash"], "native_ids_preserved": private["native_ids_preserved"],
                         "negative_controls_rejected": all(private["negative_controls"].values())})
        source_path = private["target_state"]
    return rows, evidence, Path(source_path)


def capture(output: Path, executable: str, count=40, seed=20260923, workers=4, resume=False):
    if not 1 <= workers <= 4:
        raise ValueError("workers must be between 1 and 4")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=resume)
    dataset = output / "dataset"
    dataset.mkdir(exist_ok=resume)
    chains = generate_chains(count, seed)
    rows, evidence = [], []
    bridge = Path(__file__).parent / "backends/reaper/bridge"
    for effect in bridge.glob("*.jsfx"):
        target = dataset / "Effects/Rostrum" / effect.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(effect, target)
    def capture_chain(chain):
        attempt = chain.id + "-" + uuid.uuid4().hex[:8]
        cached = _cached_chain(dataset, chain) if resume else None
        if cached:
            rows, evidence, source_path = cached
            evidence[-1]["relocated_restart"] = verify_snapshot(dataset / source_path, output / "relocated" / attempt, executable)
            print(f"{chain.id}: cached chain reverified after relocation", flush=True)
            return rows, evidence
        rows, evidence = [], []
        backend = ReaperBackend(executable, timeout=60)
        native = backend.materialize(chain.steps[0].task.initial_project, output / "workers" / attempt)
        session = backend.open(native)
        try:
            source_path = Path("states") / attempt / "00"
            source_record = snapshot(backend, session, dataset / source_path)
            previous_pcm = None
            for index, step in enumerate(chain.steps):
                before = backend.readback(session)
                if project_hash(before) != project_hash(step.task.initial_project):
                    raise ValueError("chain input differs from the declared initial state")
                session.state["renders"] = []
                environment = backend.create_environment(session, step.task.allowed_tools)
                _reference(step, environment)
                backend.commit_environment(session, environment)
                after = backend.readback(session)
                renders = session.state["renders"]
                checks = evaluate(step.task, before, after) + evaluate_renders(step.task, renders, environment.trajectory, after)
                if not checks or not all(c.passed for c in checks):
                    raise ValueError(f"{step.task.id}: {[asdict(c) for c in checks if not c.passed]}")
                target_path = Path("states") / attempt / f"{index+1:02d}"
                target_record = snapshot(backend, session, dataset / target_path, renders[-1])
                if not _stable_ids(source_record["native_ids"], target_record["native_ids"]):
                    raise ValueError("an edit changed a protected native GUID")
                pcm = renders[-1].metrics["pcm_hash"]
                if pcm == previous_pcm:
                    raise ValueError("edit did not change rendered audio")
                previous_pcm = pcm
                # Negative controls: unchanged input, and correct target with damaged protected meter.
                no_op = evaluate(step.task, before, before)
                if step.expected is None:
                    # Actual input audio with an observation, but no edit or final revision.
                    no_op += evaluate_renders(step.task, renders[:1], environment.trajectory[:3], before)
                damaged = deepcopy(after)
                damaged.meter = "3/4"
                damage_checks = evaluate(step.task, before, damaged)
                if all(c.passed for c in no_op) or all(c.passed for c in damage_checks):
                    raise ValueError("negative control unexpectedly passed")
                public_path = Path("inputs") / f"{step.task.id}.json"
                private_path = Path("private") / f"{step.task.id}.json"
                public = {"id": step.task.id, "chain_id": chain.id, "step": index, "split": chain.split,
                          "prompt": step.task.prompt, "input_state": source_path.as_posix(),
                          "allowed_tools": step.task.allowed_tools, "execution_level": step.task.execution_level}
                write_json(dataset / public_path, public)
                # Trajectory observations may contain worker paths. Relativize only the owned root.
                trajectory = json.loads(json.dumps([e.to_dict() for e in environment.trajectory]).replace(
                    str(output).replace("\\", "\\\\"), ".").replace(output.as_posix(), "."))
                private = {"task": step.task.to_dict(), "target_state": target_path.as_posix(),
                           "results": [asdict(c) for c in checks], "trajectory": trajectory,
                           "reference_kind": "procedural-control", "negative_controls": {"no_op_rejected": True, "damaged_meter_rejected": True},
                           "native_ids_preserved": True, "audio_changed": index > 0,
                           "studio": session.state["handshake"]}
                write_json(dataset / private_path, private)
                rows.append({"id": step.task.id, "chain_id": chain.id, "split": chain.split, "stage": step.task.tags[1],
                             "input": public_path.as_posix(), "private_target": private_path.as_posix()})
                evidence.append({"id": step.task.id, "passed": True, "project_hash": target_record["project_hash"],
                                 "pcm_hash": pcm, "native_ids_preserved": True, "negative_controls_rejected": True})
                source_path, source_record = target_path, target_record
                print(f"{step.task.id}: verified", flush=True)
        finally:
            backend.close(session)
        # The last state must work at a new path in a fresh process without source workspace assets.
        result = verify_snapshot(dataset / source_path, output / "relocated" / attempt, executable)
        evidence[-1]["relocated_restart"] = result
        print(f"{chain.id}: relocated restart PCM verified", flush=True)
        return rows, evidence

    def guarded(chain):
        try:
            return capture_chain(chain)
        except Exception as exc:
            write_json(output / "failures" / f"{chain.id}.json", {"chain": chain.id, "error": f"{type(exc).__name__}: {exc}"})
            print(f"{chain.id}: FAILED: {type(exc).__name__}: {exc}", flush=True)
            return None

    failures = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(guarded, chains):
            if result is None:
                failures += 1
                continue
            chain_rows, chain_evidence = result
            rows.extend(chain_rows)
            evidence.extend(chain_evidence)
    if failures:
        raise RuntimeError(f"{failures} chains failed; evidence retained. Retry with --resume in fresh worker workspaces.")
    (dataset / "samples.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8", newline="\n")
    report = {"corpus": CORPUS_VERSION, "seed": seed, "chains": count, "samples": len(rows),
              "creation_samples": count, "revision_samples": len(rows)-count,
              "splits": {s: sum(r["split"] == s for r in rows) for s in ("train", "dev", "test")},
              "passed": len(evidence), "relocated_restart_checks": count,
              "reference_kind": "procedural-control", "model_runs": "not_run", "evidence": evidence}
    write_json(dataset / "validation.json", report)
    (dataset / "README.md").write_text(
        "# REAPER linked evaluation corpus\n\n"
        "Procedural reference demonstrations; these are not model or human results.\n"
        "Each samples.jsonl row identifies a public input and private evaluation target.\n"
        "Expose only that row's inputs JSON and input state directory to an agent.\n"
        "Do not expose private/, other states, samples.jsonl, validation.json or the generator.\n"
        "Keep entire chains in their assigned split; splits measure parameter generalization, not unseen workflows.\n"
        "Each state contains a native project, Music IR, source WAVs, hashes and (except the empty state) reference audio.\n"
        "To open manually, copy Effects/Rostrum into the REAPER resource directory's Effects folder, then open project.rpp.\n"
        "The Python verifier stages the effects automatically in its isolated profile.\n"
        "Projects use relative source paths. Keep each state directory intact when moving it.\n"
        "REAPER itself is not bundled. See repository docs/reaper-corpus.md for scoring and regeneration.\n",
        encoding="utf-8", newline="\n")
    from .corpus_archive import package_dataset
    package_dataset(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reaper", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chains", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260923)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true", help="Reuse complete chains after checksum and native relocation checks")
    args = parser.parse_args()
    report = capture(args.output, args.reaper, args.chains, args.seed, args.workers, args.resume)
    print(json.dumps({k: v for k, v in report.items() if k != "evidence"}, indent=2))


if __name__ == "__main__":
    main()
