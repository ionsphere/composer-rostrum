from __future__ import annotations

import json
import hashlib
import math
import os
import re
import wave
from copy import deepcopy
from dataclasses import fields
from pathlib import Path
from typing import Any

from ...environment import MusicEnvironment
from ...models import MusicProject
from ..base import (
    BackendCapabilities,
    BackendError,
    DawOperation,
    DawSession,
    NativeProject,
    OperationResult,
    RenderArtifact,
    RenderRequest,
    RenderUnavailableError,
)
from .transport import FileBridgeTransport
from .worker import ReaperWorker
from ...audio import analyze_wav, write_fixture
from ...environment import project_hash, ToolError


class ReaperBackend:
    """Isolated native REAPER execution with strict portable-subset readback."""

    name = "reaper"
    version = "1.0"

    def __init__(self, executable: str | Path | None = None, timeout: float = 30.0,
                 expected_version: str = "7.80"):
        self.executable = executable or os.environ.get("REAPER_EXECUTABLE")
        self.timeout = timeout
        self.expected_version = expected_version
        if self.executable:
            self.capabilities = BackendCapabilities(midi_notes=True, audio_clips=True,
                native_synth=True, offline_render=True, readback=True, headless_or_unattended=True)

    # Implemented benchmark capabilities, not aspirational REAPER abilities.
    capabilities = BackendCapabilities()

    target_capabilities = BackendCapabilities(
        midi_notes=True,
        audio_clips=True,
        sampler=True,
        native_synth=True,
        native_eq=True,
        compression=True,
        sidechain=True,
        automation=True,
        offline_render=True,
        readback=True,
        headless_or_unattended=True,
    )

    def materialize(self, project: MusicProject, workspace: Path) -> NativeProject:
        workspace = Path(workspace).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "requests").mkdir(exist_ok=True)
        (workspace / "responses").mkdir(exist_ok=True)
        (workspace / "renders").mkdir(exist_ok=True)
        (workspace / "logs").mkdir(exist_ok=True)
        if self.executable:
            self.validate(project)

        source_path = workspace / "project.music-ir.json"
        if source_path.exists():
            raise BackendError("worker workspace already contains a project; use a fresh workspace or open(..., resume=True)")
        source_path.write_text(json.dumps(project.to_dict(), indent=2) + "\n", encoding="utf-8")

        # A real .rpp must be created by REAPER/the bridge, not fabricated by
        # the pure-Python bootstrap with guessed native syntax.
        native_path = workspace / "project.rpp"
        manifest_path = workspace / "reaper-worker.json"
        manifest_path.write_text(json.dumps({
            "backend": self.name,
            "backend_version": self.version,
            "status": "awaiting-reaper-worker",
            "source_music_ir": source_path.name,
            "native_project": native_path.name,
            "bridge_protocol": 1,
            "implemented_capabilities": self.capabilities.to_dict(),
            "target_capabilities": self.target_capabilities.to_dict(),
            "directories": {
                "requests": "requests",
                "responses": "responses",
                "renders": "renders",
                "logs": "logs"
            }
        }, indent=2) + "\n", encoding="utf-8")

        return NativeProject(
            backend=self.name,
            workspace=workspace,
            project_path=native_path,
            manifest_path=manifest_path,
            metadata={"source_music_ir": str(source_path), "bridge_protocol": 1},
        )

    def open(self, native: NativeProject, resume: bool = False) -> DawSession:
        if native.backend != self.name:
            raise BackendError(f"cannot open {native.backend!r} project with REAPER backend")
        session = DawSession(self.name, native, state={
            "connected": False,
            "bridge_protocol": native.metadata.get("bridge_protocol", 1),
            "renders": [],
        })
        if self.executable:
            worker = ReaperWorker(self.executable, native.workspace)
            pending = [p for p in (native.workspace / "requests").glob("*.json")
                       if not (native.workspace / "responses" / p.name).exists()]
            if pending:
                raise BackendError("workspace has unacknowledged requests; use a fresh workspace after uncertain execution")
            session.state["worker"] = worker
            try:
                worker.start()
                self.connect(session, timeout=self.timeout)
                if resume:
                    if not native.project_path.is_file():
                        raise BackendError("cannot resume a missing native project")
                    self._request(session, "reopen")
                else:
                    project = MusicProject.from_dict(json.loads(Path(native.metadata["source_music_ir"]).read_text(encoding="utf-8")))
                    self._write_project(session, project)
                manifest = json.loads(native.manifest_path.read_text(encoding="utf-8"))
                manifest.update(status="connected", handshake=session.state["handshake"],
                    instrument={"name": "Rostrum deterministic sine v1", "sha256": hashlib.sha256(
                        (Path(__file__).parent / "bridge" / "rostrum_sine.jsfx").read_bytes()).hexdigest()})
                manifest["studio_files"] = {p.relative_to(native.workspace).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for folder in (native.workspace / "bridge", native.workspace / "assets")
                    for p in folder.glob("*") if p.is_file()}
                native.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            except BaseException:
                worker.close()
                raise
        return session

    def connect(self, session: DawSession, transport: Any | None = None, timeout: float = 10.0) -> dict[str, Any]:
        if session.closed:
            raise BackendError("DAW session is already closed")
        worker = session.state.get("worker")
        bridge = transport or FileBridgeTransport(session.native_project.workspace,
                                                  health_check=worker.check if worker else None)
        pong = bridge.request("ping", timeout=timeout)
        handshake = bridge.request("capabilities", timeout=timeout)
        if not isinstance(pong, dict) or pong.get("protocol") != 1 or not pong.get("pong"):
            raise BackendError("invalid REAPER bridge ping response")
        if not isinstance(handshake, dict) or handshake.get("protocol") != 1:
            raise BackendError("invalid REAPER bridge capabilities handshake")
        if not isinstance(handshake.get("capabilities"), dict):
            raise BackendError("REAPER bridge handshake omitted capabilities")
        if self.executable and handshake.get("reaper_version", "").split("/")[0] != self.expected_version:
            raise BackendError(f"reference studio requires REAPER {self.expected_version}; got {handshake.get('reaper_version')}")
        session.state.update({
            "connected": True,
            "transport": bridge,
            "handshake": handshake,
            "live_capabilities": dict(handshake["capabilities"]),
        })
        session.state["capabilities"] = BackendCapabilities(**{
            f.name: handshake["capabilities"].get(f.name) is True for f in fields(BackendCapabilities)})
        return handshake

    def create_environment(self, session: DawSession, allowed_tools: list[str]) -> MusicEnvironment:
        self._require_bridge(session)
        return ReaperEnvironment(self, session, allowed_tools)

    def commit_environment(self, session: DawSession, environment: MusicEnvironment) -> None:
        self._require_bridge(session)
        if project_hash(environment.project) != project_hash(self.readback(session)):
            raise BackendError("environment/native project drift")

    def execute(self, session: DawSession, operation: DawOperation) -> OperationResult:
        self._require_bridge(session)
        before = self.readback(session)
        env = MusicEnvironment(before, [operation.name])
        result = env.call(operation.name, **operation.arguments)
        changed = project_hash(before) != project_hash(env.project)
        if changed:
            self._write_project(session, env.project)
        return OperationResult(operation.name, result, changed)

    def readback(self, session: DawSession) -> MusicProject:
        self._require_bridge(session)
        data = self._request(session, "readback")
        for asset in data.get("assets", []):
            asset.pop("path", None)
        return MusicProject.from_dict(data)

    def save(self, session: DawSession) -> NativeProject:
        self._require_bridge(session)
        self._request(session, "save")
        if not session.native_project.project_path.is_file():
            raise BackendError("REAPER did not save the native project")
        return session.native_project

    def render(self, session: DawSession, request: RenderRequest) -> RenderArtifact:
        self._require_bridge(session)
        if request.format != "wav" or request.scope != "project" or request.channels not in (1, 2):
            raise RenderUnavailableError("only project-scope mono/stereo PCM WAV renders are supported")
        if request.sample_rate not in (44100, 48000, 96000):
            raise RenderUnavailableError("unsupported sample rate")
        if request.start is not None and (not math.isfinite(request.start) or request.start < 0):
            raise RenderUnavailableError("invalid render start")
        if request.end is not None and (not math.isfinite(request.end) or request.end <= (request.start or 0)):
            raise RenderUnavailableError("invalid render end")
        self.save(session)
        state_hash = project_hash(self.readback(session))
        existing_ids = [int(p.stem[1:]) for p in (session.native_project.workspace / "renders").glob("r*.wav")
                        if p.stem[1:].isdigit()]
        render_id = f"r{max(existing_ids, default=0) + 1:04d}"
        path = session.native_project.workspace / "renders" / f"{render_id}.wav"
        if path.exists():
            raise BackendError("refusing to overwrite an immutable render")
        self._request(session, "render", {**request.to_dict(), "render_id": render_id})
        try:
            metrics = analyze_wav(path)
        except (OSError, ValueError, EOFError, wave.Error) as exc:
            raise BackendError(f"invalid REAPER render: {exc}") from exc
        if metrics["sample_rate"] != request.sample_rate or metrics["channels"] != request.channels:
            raise BackendError("REAPER render settings did not match request")
        artifact = RenderArtifact(render_id, self.name, state_hash, path, metrics["content_hash"], request,
            metrics["duration_seconds"], metrics["sample_rate"], metrics["channels"], metrics,
            {"native_project_hash": hashlib.sha256(session.native_project.project_path.read_bytes()).hexdigest(),
             "handshake": session.state["handshake"]})
        session.state["renders"].append(artifact)
        path.with_suffix(".json").write_text(json.dumps(artifact.to_dict(), indent=2), encoding="utf-8")
        return artifact

    def close(self, session: DawSession) -> None:
        try:
            if "worker" in session.state:
                session.state["worker"].close()
        finally:
            session.closed = True

    def _request(self, session: DawSession, command: str, arguments: dict | None = None):
        self._require_bridge(session)
        return session.state["transport"].request(command, arguments, timeout=self.timeout)

    def _write_project(self, session: DawSession, project: MusicProject) -> None:
        self.validate(project)
        data = deepcopy(project.to_dict())
        for asset in data["assets"]:
            path = session.native_project.workspace / "assets" / f"{asset['id']}.wav"
            if not path.exists():
                write_fixture(path, float(asset["duration_seconds"]))
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if asset.get("content_hash") and asset["content_hash"] != actual_hash:
                raise BackendError("fixture content hash does not match the declared asset")
            asset["path"] = path.as_posix()
        self._request(session, "materialize", {"project": data})
        actual = self.readback(session)
        if actual.to_dict() != project.to_dict():
            from ...environment import _diff_paths
            raise BackendError(f"native round-trip drift: {_diff_paths(project.to_dict(), actual.to_dict())}")

    @staticmethod
    def validate(project: MusicProject) -> None:
        """Reject unsupported semantics instead of silently rendering a different project."""
        if not math.isfinite(project.tempo) or not 20 <= project.tempo <= 300:
            raise BackendError("REAPER subset supports tempo 20–300 BPM")
        if not re.fullmatch(r"[1-9][0-9]?/(1|2|4|8|16|32)", project.meter):
            raise BackendError("unsupported meter")
        def ids(items):
            seen = set()
            for item in items:
                identity = item.get("id", "")
                if not re.fullmatch(r"[A-Za-z0-9_-]+", identity) or identity in seen:
                    raise BackendError("missing, unsafe, or duplicate stable ID")
                seen.add(identity)
        def keys(item, supported):
            extra = set(item) - set(supported.split())
            if extra:
                raise BackendError(f"unsupported native fields: {sorted(extra)}")
        ids(project.tracks)
        ids(project.assets)
        for asset in project.assets:
            keys(asset, "id kind name duration_seconds provenance content_hash")
            if asset.get("provenance", {}).get("source") != "procedural_fixture":
                raise BackendError("only benchmark-owned procedural audio fixtures are currently supported")
            duration = asset.get("duration_seconds", 0)
            if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 < duration <= 30:
                raise BackendError("fixture duration must be in (0, 30] seconds")
        for track in project.tracks:
            keys(track, "id name kind muted gain_db pan clips instruments effects sends automation")
            if track.get("kind") not in ("midi", "audio"):
                raise BackendError("unsupported track kind")
            if any(track.get(key) for key in ("instruments", "automation")):
                raise BackendError("custom instruments and automation are not yet supported")
            ids(track.get("effects", []))
            for effect in track.get("effects", []):
                keys(effect, "id type gain_db")
                if effect.get("type") != "gain" or not -120 <= effect.get("gain_db", 0) <= 24:
                    raise BackendError("only bounded gain effects are currently supported")
            destinations = set()
            for send in track.get("sends", []):
                keys(send, "destination_id gain_db")
                destination = send.get("destination_id")
                if destination in destinations or destination == track["id"] or destination not in {t["id"] for t in project.tracks}:
                    raise BackendError("invalid or duplicate routing destination")
                if not -120 <= send.get("gain_db", 0) <= 24:
                    raise BackendError("invalid send gain")
                destinations.add(destination)
            gain = track.get("gain_db", 0)
            if not math.isfinite(gain) or not -120 <= gain <= 24:
                raise BackendError("track gain must be between -120 and 24 dB")
            if not -1 <= track.get("pan", 0) <= 1:
                raise BackendError("track pan must be between -1 and 1")
            ids(track.get("clips", []))
            for clip in track.get("clips", []):
                if clip.get("kind") == "midi":
                    keys(clip, "id kind start length notes")
                    if any(not math.isfinite(clip[k]) or abs(clip[k]*960-round(clip[k]*960)) > 1e-6 for k in ("start", "length")):
                        raise BackendError("native MIDI clip timing must lie on the 960 ticks/quarter grid")
                    if clip["start"] < 0 or clip["length"] <= 0:
                        raise BackendError("invalid MIDI clip extent")
                    ids(clip.get("notes", []))
                    for note in clip.get("notes", []):
                        keys(note, "id pitch velocity start duration channel")
                        if type(note["pitch"]) is not int or type(note["velocity"]) is not int or not 0 <= note["pitch"] <= 127 or not 1 <= note["velocity"] <= 127:
                            raise BackendError("invalid MIDI pitch/velocity")
                        if note.get("channel", 0) != 0:
                            raise BackendError("reference instrument supports MIDI channel 0")
                        if any(not math.isfinite(note[k]) or abs(note[k]*960-round(note[k]*960)) > 1e-6 for k in ("start", "duration")):
                            raise BackendError("native MIDI timing must lie on the 960 ticks/quarter grid")
                        if note["start"] < 0 or note["duration"] <= 0 or note["start"] + note["duration"] > clip["length"]:
                            raise BackendError("note must fit inside its clip")
                else:
                    keys(clip, "id kind asset_id timeline_start_beats source_start source_end pitch_semitones stretch_ratio reversed fade_in_seconds fade_out_seconds")
                    if clip.get("reversed"):
                        raise BackendError("native sample reversal is not yet supported")
                    asset = next((a for a in project.assets if a["id"] == clip.get("asset_id")), None)
                    if asset is None or not 0 <= clip["source_start"] < clip["source_end"] <= asset["duration_seconds"]:
                        raise BackendError("invalid audio source range")
                    if not 0.1 <= clip.get("stretch_ratio", 1) <= 10:
                        raise BackendError("unsupported audio stretch ratio")
                    if not -48 <= clip.get("pitch_semitones", 0) <= 48 or clip.get("timeline_start_beats", 0) < 0:
                        raise BackendError("invalid sample pitch or timeline start")
                    duration = (clip["source_end"] - clip["source_start"]) * clip.get("stretch_ratio", 1)
                    if any(not math.isfinite(clip.get(k, 0)) or not 0 <= clip.get(k, 0) <= duration
                           for k in ("fade_in_seconds", "fade_out_seconds")):
                        raise BackendError("fade lengths must fit inside the audio item")
        graph = {t["id"]: [s["destination_id"] for s in t.get("sends", [])] for t in project.tracks}
        def visit(node, stack):
            if node in stack:
                raise BackendError("feedback routing is not supported")
            for destination in graph[node]:
                visit(destination, stack | {node})
        for node in graph:
            visit(node, set())

    @staticmethod
    def _require_bridge(session: DawSession) -> None:
        if session.closed:
            raise BackendError("DAW session is already closed")
        if not session.state.get("connected"):
            raise BackendError(
                "REAPER worker is not connected; materialization currently creates only the worker bundle"
            )


class ReaperEnvironment(MusicEnvironment):
    def __init__(self, backend: ReaperBackend, session: DawSession, allowed_tools: list[str]):
        super().__init__(backend.readback(session), allowed_tools)
        self.backend, self.session = backend, session

    def call(self, tool: str, **arguments: Any) -> Any:
        if tool in ("render", "inspect_render", "analyze_render"):
            return super().call(tool, **arguments)
        self._project = self.backend.readback(self.session)
        previous = self.project
        result = super().call(tool, **arguments)
        if project_hash(previous) != project_hash(self._project):
            try:
                self.backend.validate(self._project)
            except BackendError as exc:
                self._project = previous
                event = self.trajectory[-1]
                event.after_hash, event.changed_paths = event.before_hash, []
                event.error = f"ToolError: {exc}"
                raise ToolError(str(exc)) from exc
            try:
                self.backend._write_project(self.session, self._project)
                self._project = self.backend.readback(self.session)
            except Exception as exc:
                self.trajectory[-1].error = f"{type(exc).__name__}: {exc}"
                raise
        return result

    def _tool_render(self, **arguments):
        self._project = self.backend.readback(self.session)
        return self.backend.render(self.session, RenderRequest(**arguments)).to_dict()

    def _tool_inspect_render(self, render_id: str):
        for artifact in self.session.state["renders"]:
            if artifact.render_id == render_id:
                return artifact.to_dict()
        raise ToolError(f"unknown render: {render_id}")

    def _tool_analyze_render(self, render_id: str):
        artifact = self._tool_inspect_render(render_id)
        return {"render_id": render_id, "project_hash": artifact["project_hash"], **artifact["metrics"]}
