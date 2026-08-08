# Architecture

## Goal

Composer Rostrum separates **musical intelligence** from **DAW implementation details**. Agents operate against a stable tool/environment contract and a canonical project representation. Backends are adapters.

## Core components

### 1. Music IR
A serializable representation for tempo, meter, key, tracks, clips, notes, instruments, routing, effects, automation, and metadata. The first scaffold contains only the fields needed for L0 tasks; it should grow under versioned schemas rather than by embedding DAW-specific blobs.

### 2. Task
A task contains:
- immutable ID and benchmark level;
- natural-language producer/composer request;
- initial project state;
- allowed tool surface;
- evaluator specifications;
- tags/provenance.

Hidden benchmark fixtures may additionally carry oracle state, procedural-generator seeds, or private evaluation assets.

### 3. Environment
The environment owns project state and exposes bounded tools such as:

```text
inspect_project
inspect_track
set_tempo
create_track
add_notes
move_notes
set_velocity
add_effect
set_parameter
route_signal
render
analyze_audio
listen
undo
```

The agent should not receive evaluator internals or oracle answers.

### 4. Agent adapter
A provider-neutral interface accepts a task and environment. Adapters can wrap frontier LLMs, local models, scripted baselines, or trained music agents. All tool interactions should be logged in a normalized trajectory format.

### 5. Backends
The initial logical backend is in-memory Music IR. The first real DAW backend should likely target REAPER because it has a broad scripting API. Later adapters can target MIDI, FL Studio, Ableton, Logic, or headless audio engines.

Backend conformance tests must ensure the same semantic operation produces equivalent Music IR/project effects.

### 6. Evaluators
Evaluators are composable and should report both a score and diagnostics:
- exact project properties;
- symbolic music constraints;
- preservation/no-regression constraints;
- routing/effect graph constraints;
- rendered-audio measurements;
- perceptual/embedding models;
- judge models;
- human preference.

A benchmark task should use the least subjective evaluator capable of measuring its requirement.

## Run artifact

Every run should eventually produce an auditable artifact:

```json
{
  "task_id": "...",
  "agent": "...",
  "environment_version": "...",
  "trajectory": [],
  "project_before_hash": "...",
  "project_after_hash": "...",
  "renders": [],
  "evaluator_results": [],
  "score": 0.0,
  "tokens": {},
  "latency": {},
  "cost": {}
}
```

This lets us answer not only whether an agent passed, but *how* it behaved: number of edits, unnecessary changes, retries, listening behavior, token use, and cost.

## Training direction

The benchmark should bootstrap training data rather than depend on a pre-existing corpus:

1. procedurally generate valid projects;
2. apply known mutations or define requested transformations;
3. derive natural-language issues;
4. solve with scripted experts or strong agents;
5. retain successful trajectories;
6. later add opt-in human producer trajectories.

This creates the music analogue of issue/patch/test histories while keeping provenance explicit.
