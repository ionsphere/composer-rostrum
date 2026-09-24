# Roadmap

## Phase 0 — executable scaffold

- [x] Define benchmark thesis and levels
- [x] Define initial Music IR and task objects
- [x] Add agent protocol and reference agent
- [x] Add exact-property and preservation evaluators
- [x] Add CLI and seed task
- [x] Add CI

## Phase 1 — Rostrum-100

Goal: answer **how capable are general-purpose reasoning agents at bounded music-production work today?**

- [x] build a real environment tool surface instead of direct object mutation;
- [x] add trajectory/event logging;
- [x] add deterministic L0 mechanics suite;
- [x] add deterministic L1 symbolic suite;
- [x] add multi-step dependent-edit suite;
- [x] add sample-manipulation/provenance fixtures;
- [x] expand to 10-15 stable task families with benchmark splits (Rostrum-120: twelve families);
- [x] add mutation/oracle system;
- [x] add negative/reference solvers;
- [x] build benchmark reporting by level/family/failure class;
- [ ] run at least three general-purpose agent/model configurations.

Exit criterion: 100+ stable tasks, reproducible scoring, and a useful failure taxonomy.

## Phase 2 — symbolic musicianship

- [x] stable MIDI note/clip identity;
- [x] chord/scale evaluators;
- [x] quantization/transposition/repair tasks;
- [x] relational preservation evaluators;
- [ ] voice-leading evaluators;
- [ ] rhythmic similarity metrics;
- [ ] MIDI import/export;
- [ ] larger procedurally generated suites.

## Phase 3 — first DAW backend (in progress)

Target REAPER first. See [daw-execution-plan.md](daw-execution-plan.md).

- [x] define `DawBackend`, native-project/session, operation, capability, and render-artifact contracts;
- [x] route the existing benchmark runner through an `InMemoryBackend` lifecycle;
- [x] add task execution levels E0-E4 and backend capability requirements;
- [x] scaffold `ReaperBackend` workspace/manifest lifecycle;
- [x] define REAPER bridge protocol v1;
- [x] add Lua bridge bootstrap with `ping`/`capabilities` dispatch;
- [x] implement Python ↔ Lua workspace transport and live handshake;
- [x] materialize a minimal `.rpp` from Music IR through the worker;
- [x] map stable Rostrum IDs to REAPER tracks/items/notes;
- [x] read supported project state back into canonical IR;
- [x] automate REAPER worker launch/reset/timeout handling;
- [x] render a deterministic MIDI phrase to a genuine WAV;
- [x] verify edit → re-render changes audio while preserving protected state;
- [x] add deterministic instrument/plugin fixture manifest;
- [x] build Rostrum-DAW-20.
- [x] add native track/clip creation and linear audio fades;
- [x] add linked creation/revision corpus capture with portable native snapshots;
- [x] add native-input evaluation, whole-chain splits and reference/negative controls.

The implemented subset and remaining trial-period coverage work are tracked in
[reaper-studio.md](reaper-studio.md). Full sampler, automation, routing/effect and
hybrid production coverage remains open. Actual model comparisons still require
provider credentials and selected configurations; see [benchmark-runs.md](benchmark-runs.md).

The first critical exit milestone is **DAW build loop complete**: Music IR → real REAPER project → deterministic instrument → offline render → valid non-silent WAV → edit → second render → measurable/hash difference.

## Phase 4 — audio evaluation

- [x] WAV metadata/file validation, full-file and PCM hashes;
- [x] silence/peak/RMS measurements;
- LUFS/true-peak/crest/dynamics measurements;
- spectral masking and band-energy metrics;
- transient and stereo metrics;
- [x] rendered before/after RMS comparisons and causal feedback checks;
- tasks with multiple acceptable production solutions.

## Phase 5 — listen/critique/revise agency

Give agents an explicit render/listen/analyze loop and measure whether feedback improves outcomes. Separate:

1. agents that edit once;
2. agents that render but do not react usefully;
3. agents that diagnose audio correctly;
4. agents that iteratively converge.

## Phase 6 — perceptual and compositional evaluation

Only after lower levels are reliable:

- controlled humanization tasks;
- arrangement/tension/density tasks;
- critic-model experiments;
- pairwise human preference calibration;
- L4 constrained composition benchmark.

## Phase 7 — training data

Use successful benchmark and opt-in human trajectories to investigate specialization:

The [REAPER corpus](reaper-corpus.md) provides procedural reference trajectories
and prompt → project / prompt + project → revised-project pairs. Human and real
model trajectories remain separate future sources.

- supervised tool-use traces;
- rejection sampling from benchmark evaluators;
- reinforcement learning on deterministic environments;
- preference training for perceptual/compositional tasks.

The project should make it possible to demonstrate a training gain against a held-out benchmark rather than merely demonstrate attractive examples.

## Open research questions

- What is the minimum Music IR that remains portable across DAWs?
- Which production outcomes can be objectively measured well enough for RL?
- How do we score preservation when several musically valid edits exist?
- What audio representation gives an LLM/agent useful listening feedback?
- At what level do general models fail because of musical knowledge rather than environment/tool grounding?
- How should benchmark contamination be detected once task generators are public?
- How much expert trajectory data is needed before specialization beats stronger general models?
