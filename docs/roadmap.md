# Roadmap

## Phase 0 — executable scaffold

- [x] Define benchmark thesis and levels
- [x] Define initial Music IR and task objects
- [x] Add agent protocol and reference agent
- [x] Add exact-property and preservation evaluators
- [x] Add CLI and seed task
- [ ] Add CI

## Phase 1 — Rostrum-100

Goal: answer **how capable are general-purpose reasoning agents at bounded music-production work today?**

- implement 10-15 deterministic task families;
- add procedural project/task generators with fixed seeds;
- add a mutation/oracle system;
- create train/dev/public-test/private-test splits;
- build a real environment tool surface instead of direct object mutation;
- add trajectory/event logging;
- add negative/reference solvers;
- build benchmark reporting by level/family/failure class;
- run at least three general-purpose agent/model configurations.

Exit criterion: 100 stable tasks, reproducible scoring, and a useful failure taxonomy.

## Phase 2 — symbolic musicianship

- richer note/clip/automation IR;
- chord/scale/voice-leading evaluators;
- rhythmic similarity and preservation metrics;
- MIDI import/export;
- larger procedurally generated suites.

## Phase 3 — first DAW backend

Target REAPER first unless experiments reveal a better headless environment.

- bridge Music IR operations to ReaScript;
- read project state back into canonical IR;
- render stems/mix headlessly where feasible;
- backend conformance tests;
- deterministic plugin/instrument fixture set.

## Phase 4 — audio evaluation

- LUFS/true-peak/crest/dynamics measurements;
- spectral masking and band-energy metrics;
- transient and stereo metrics;
- rendered before/after comparisons;
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
