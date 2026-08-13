# DAW Execution and Render Feedback Plan

## Goal

Composer Rostrum already measures musical reasoning against a DAW-independent Music IR. The next major milestone is to measure whether an agent can take that reasoning into a real production environment, create a native project, render it, inspect/listen to the produced audio, diagnose remaining problems, and revise the project.

The target loop is the music-production analogue of edit/build/test/debug in software engineering:

```text
producer request
      ↓
inspect native project
      ↓
make bounded edits
      ↓
render / bounce
      ↓
WAV + render diagnostics
      ↓
listen / analyze
      ↓
revise
      ↓
render again
      ↓
final project + audio + trajectory + score
```

The rendered sound is not merely an output attachment. It is an observation available to the agent and a first-class benchmark artifact.

## Two benchmark axes

Keep musical difficulty and execution difficulty separate.

### Musical level (existing)

- L0 — mechanics
- L1 — symbolic musicianship
- L2 — production
- L3 — perceptual editing
- L4 — constrained/open composition

### Execution level (new)

- **E0 — backend conformance:** Music IR can be materialized/read back without semantic loss in the supported portable subset.
- **E1 — native project manipulation:** agent edits a real DAW session and can save/reopen it.
- **E2 — render correctness:** edits produce a valid non-silent render with expected structural/audio properties.
- **E3 — listen-and-revise:** agent renders, consumes audio observations, diagnoses a defect, edits, and improves a measurable target.
- **E4 — open production:** multi-step hybrid MIDI/audio/sampler/effects work with iterative listening and several acceptable solutions.

A benchmark result should eventually report both dimensions, for example `L2/E3`.

## Architectural boundary

Music IR must remain the portable semantic representation. Native DAW state is a backend concern.

```text
                  Rostrum Agent
                       │
                  MusicEnvironment
                       │
                  DawBackend API
                       │
        ┌──────────────┼───────────────┐
        │              │               │
  InMemoryBackend  ReaperBackend   future backends
        │              │          FL/Ableton/Logic
        │              │
    Music IR       native .rpp
                       │
                    REAPER
                       │
                 rendered WAV
```

Do not make `.rpp`, `.flp`, or another native project format the canonical model representation.

## Core backend contract

A backend should expose lifecycle rather than merely format conversion:

```python
class DawBackend(Protocol):
    name: str
    capabilities: BackendCapabilities

    def materialize(self, project: MusicProject, workspace: Path) -> NativeProject: ...
    def open(self, native: NativeProject) -> DawSession: ...
    def execute(self, session: DawSession, operation: DawOperation) -> OperationResult: ...
    def readback(self, session: DawSession) -> MusicProject: ...
    def save(self, session: DawSession) -> NativeProject: ...
    def render(self, session: DawSession, request: RenderRequest) -> RenderArtifact: ...
    def close(self, session: DawSession) -> None: ...
```

`MusicEnvironment` remains the benchmark-facing tool boundary. The agent should not directly manipulate backend objects or native files unless a benchmark explicitly tests raw project-file editing.

## Capability negotiation

Backends differ dramatically. Tasks therefore declare semantic requirements rather than assuming every DAW can perform every operation.

Example capabilities:

```yaml
midi_notes: true
audio_clips: true
sampler: true
native_synth: true
native_eq: true
compression: true
sidechain: true
automation: true
offline_render: true
readback: true
headless_or_unattended: true
```

The runner must skip/invalidate a backend-task pairing when required capabilities are absent; it must never silently downgrade a task.

## Render artifact

Every render is immutable and tied to the exact project state that produced it.

```json
{
  "render_id": "...",
  "project_hash": "...",
  "backend": "reaper",
  "native_project_hash": "...",
  "path": "renders/r0002.wav",
  "content_hash": "...",
  "duration_seconds": 14.81,
  "sample_rate": 48000,
  "channels": 2,
  "request": {"scope": "project"},
  "metrics": {},
  "created_at": "..."
}
```

The trajectory records the render event before any listening or analysis event so we can reconstruct exactly what observation informed the next edit.

## Listening and analysis layers

Do not collapse all feedback into one opaque `listen()` call. Rostrum should support increasingly rich observation modes:

1. **metadata:** duration, sample rate, channels, file validity;
2. **DSP measurements:** peak, RMS/LUFS, silence, clipping, crest factor;
3. **domain analyzers:** pitch, onset/transient, spectrum, masking, stereo, tempo alignment;
4. **audio-capable model observation:** agent receives the render acoustically;
5. **human preference:** only for tasks whose target cannot be adequately specified otherwise.

This enables controlled comparisons between agents with no audio perception, structured DSP feedback, and native audio understanding.

## Reference studio

Reproducibility requires a versioned production environment analogous to a pinned compiler/toolchain image.

### Rostrum Studio v1 target

- pinned REAPER version;
- clean portable/user profile per worker;
- REAPER-native effects first;
- one deterministic/free instrument path for MIDI-to-audio rendering;
- Rostrum-owned synthetic/CC0 sample fixture pack;
- fixed sample rate and render settings;
- no arbitrary user plugins in benchmark workers;
- explicit plugin/version manifest included in every run artifact.

Third-party instruments such as Surge XT can be introduced only after the native/minimal path is stable.

## Why REAPER first

REAPER is the first research backend because it offers a broad scripting surface, a portable project format, mature offline rendering, and a relatively small installation footprint. The purpose is not to declare it the universal target; it is the controlled environment in which the full agent-edit-render-listen loop can first become reproducible.

Later backends are intentionally allowed to be harder. FL Studio, Ableton, and Logic can test whether agency transfers to applications whose supported automation surfaces differ or require hybrid API/UI operation.

## REAPER control architecture

Keep the benchmark harness in Python and run a persistent Lua bridge inside REAPER:

```text
Python Rostrum worker
       │
       │ JSON request/response transport
       ▼
rostrum_bridge.lua
       │
       ▼
REAPER/ReaScript API
```

The transport should initially be deliberately boring and debuggable: workspace request/response files or localhost JSON-lines socket. Do not start with UI automation.

Bridge responsibilities:

- handshake/version/capabilities;
- inspect project/tracks/items/takes/notes;
- apply supported semantic operations;
- save project;
- initiate render;
- return render status/errors;
- expose stable native identifiers mapped to Rostrum IDs;
- never expose hidden evaluators/oracle data.

## Worker lifecycle

A real DAW benchmark worker is stateful and must be reset between runs.

```text
create isolated workspace/profile
→ stage fixture assets
→ materialize native project
→ launch REAPER
→ establish bridge handshake
→ open project
→ run agent trajectory
→ save final project
→ render requested artifacts
→ collect logs/projects/renders
→ terminate REAPER
→ archive run artifact
→ destroy workspace/profile
```

The worker must detect dialogs, plugin-scan failures, render failures, crashes, and stale sessions as infrastructure failures distinct from agent failures.

## Run artifact extension

Extend current trajectories with:

- backend name/version;
- reference-studio manifest;
- native project hashes;
- session/bridge events;
- render events and audio hashes;
- analysis/listening observations;
- render count and time;
- infrastructure failures separately from evaluator failures.

This data later becomes training material of the form:

```text
project state + rendered observation + diagnosis + edit + new render + reward delta
```

## Implementation path

### Phase A — backend abstraction (start now)

1. Add backend/session/render dataclasses and `DawBackend` protocol.
2. Implement `InMemoryBackend` as the conformance/reference backend.
3. Keep current benchmark behavior working through this abstraction.
4. Add backend capability declarations and tests.
5. Add render artifact/event types even though in-memory backend cannot produce real audio.

Exit criterion: existing L0/L1/multi-step tests pass with a backend-aware runner.

### Phase B — REAPER project materialization

1. Add `ReaperBackend` package.
2. Define workspace/native-project lifecycle.
3. Generate/open a minimal native project from Music IR using the smallest robust path.
4. Establish stable Rostrum-ID ↔ REAPER-object mapping.
5. Read back tempo/tracks/MIDI notes into Music IR.

Exit criterion: a project containing a MIDI phrase round-trips through REAPER without semantic drift in supported fields.

### Phase C — bridge + real worker

1. Add persistent `rostrum_bridge.lua`.
2. Add handshake and command protocol.
3. Implement inspect/edit/save commands.
4. Build worker launch/reset/timeout/error handling.
5. Add integration-test marker so ordinary CI can skip machines without REAPER.

Exit criterion: an automated test launches REAPER, edits one MIDI note through the bridge, saves, closes, reopens, and verifies readback.

### Phase D — first genuine build-to-sound test

Create one benchmark-owned fixture:

> materialize a four-note MIDI phrase → load deterministic instrument → render → verify WAV exists and is non-silent.

Then edit one note, re-render, and verify:

- project hash changed;
- render hash changed;
- render remains valid/non-silent;
- unrelated project state stayed unchanged.

This is the first milestone that deserves the label **DAW build loop complete**.

### Phase E — audio observation

1. Add WAV metadata parser.
2. Add deterministic peak/RMS/silence/clipping measurements.
3. Add immutable render registry tied to project hashes.
4. Add `inspect_render` and `analyze_render` environment tools.
5. Later add native model listening.

Exit criterion: an agent can render, receive a structured observation, and make a second edit based on it.

### Phase F — Rostrum-DAW-20

Build 20 initial real-DAW tasks:

- 5 MIDI/project manipulation;
- 5 sample/sampler workflow;
- 5 routing/effect/mix tasks;
- 5 render-listen-revise tasks.

Report success separately for semantic correctness, native execution, render success, preservation, and feedback-loop improvement.

### Phase G — additional DAWs

Only after REAPER E0-E3 is stable:

- implement capability probes for FL Studio/Ableton/Logic;
- select the least fragile supported control path for each;
- run the same portable tasks where capabilities overlap;
- add backend-specific tasks only when necessary.

## Benchmark integrity rules

1. A backend error is not automatically an agent failure; infrastructure status must be recorded separately.
2. A native project that saves but renders silence fails an E2 task.
3. A render that sounds acceptable but violates protected project state can fail preservation.
4. Agents never receive evaluator internals.
5. Render/listen observations must be causally ordered in trajectories.
6. Native project editing and GUI automation are separate capabilities and should be benchmarked explicitly if introduced.
7. The benchmark environment/plugin manifest is part of reproducibility and must be versioned.
8. External sample acquisition remains a later open-world capability and retains the provenance/license requirements already defined elsewhere.

## Immediate repository work

The first implementation commit following this document should introduce:

- `backends/base.py` — protocol and common dataclasses;
- `backends/memory.py` — reference backend;
- `backends/reaper/` — capability declaration, native-project/workspace skeleton, and Lua bridge protocol stub;
- backend-aware runner/run-artifact fields;
- unit tests for backend lifecycle/capability checks;
- an integration-test contract for the future real REAPER worker.

The next externally visible milestone after that is not another schema. It is a WAV produced by a real REAPER worker from a benchmark-owned Music IR project.