# Composer Rostrum

**A benchmark and execution harness for measuring AI agency in music composition and production.**

Composer Rostrum is a word-play on SWE-bench: instead of asking an agent to repair a software repository from an issue, Rostrum gives an agent a music-production project, a natural-language request, a constrained set of tools, and executable evaluators.

The central question is not "can a model generate music?" It is:

> Given an existing musical state and a producer/composer request, can an AI agent inspect the project, make the right bounded changes, listen to the result, and verify that it solved the request without damaging unrelated work?

## Why this project exists

End-to-end audio generation entangles composition, performance, sound design, mixing, and mastering. It also makes precise editing and objective evaluation awkward. Composer Rostrum instead treats music creation as an **agent-environment problem**, analogous to coding agents:

```text
Software agent                         Music agent
--------------                         -----------
repository                             project
issue                                  producer request
files / AST                            Music IR
editor + shell                         composition/DAW tools
unit/integration tests                 symbolic/audio/project evaluators
patch                                  project delta
CI result                              benchmark score
```

The benchmark is deliberately **not tied to generated waveforms or to one DAW**. A canonical Music IR represents the project. Backends can translate it into REAPER, FL Studio, Ableton, Logic, MIDI, or future environments.

## Initial benchmark ladder

| Level | Capability | Example | Evaluation |
|---|---|---|---|
| L0 | DAW mechanics | "Mute drums and duplicate bars 5-8" | exact project state |
| L1 | musical syntax | "Resolve the final chord to C minor" | symbolic/theory constraints |
| L2 | production | "Make the kick audible over the bass" | audio + preservation metrics |
| L3 | perceptual editing | "Make these drums less robotic without changing the groove" | structural + perceptual metrics |
| L4 | composition | "Write an 8-bar bass line that builds tension into the chorus" | multi-evaluator / human preference |

The first milestone intentionally emphasizes L0-L2. We should learn how far general reasoning models get **before training a specialized music model**.

## Design principles

1. **Benchmark first, model later.** Establish repeatable tasks and scores before fine-tuning.
2. **Edits over blank-page generation.** The SWE-bench-shaped unit is an existing project plus a requested change.
3. **Executable ground truth where possible.** Early tasks should have deterministic or property-based evaluators.
4. **Procedural task generation.** Generate valid projects, inject controlled defects or requested transformations, and retain the hidden oracle state.
5. **Preservation matters.** Solving the requested problem while changing unrelated music is a failure mode.
6. **Backend independence.** Intelligence targets Music IR and tools, not proprietary GUI coordinates.
7. **Auditability.** Record every observation, tool call, project delta, render, evaluator result, and token/cost statistic.
8. **Copyright-clean benchmark core.** The baseline benchmark should be synthesizable from procedural, public-domain, or explicitly licensed material and should not require commercial recordings.

## Repository layout

```text
composer-rostrum/
├── docs/
│   ├── architecture.md
│   ├── benchmark.md
│   └── roadmap.md
├── examples/tasks/
│   └── L0-001-set-tempo.json
├── schemas/
│   ├── music-ir.schema.json
│   └── task.schema.json
├── src/composer_rostrum/
│   ├── agent.py
│   ├── evaluator.py
│   ├── models.py
│   └── runner.py
├── tests/
│   └── test_smoke.py
└── pyproject.toml
```

## Target execution loop

```text
Task
  │
  ├── initial Music IR
  ├── natural-language request
  ├── allowed tools
  └── evaluators
  │
  ▼
Agent ── observe / edit / render / listen ──► Environment
  ▲                                            │
  └──────────────── observations ──────────────┘
                                               │
                                               ▼
                                         Evaluators
                                               │
                                      score + diagnostics
```

## Quick start

The scaffold currently uses only Python's standard library for the executable core.

```bash
python -m pip install -e .
rostrum examples/tasks/L0-001-set-tempo.json
```

The initial runner includes a deliberately trivial reference agent so we can validate benchmark plumbing independently of any model provider.

## Near-term milestone

Build **Rostrum-100**: roughly 100 deterministic tasks across 10-15 task families, then run several general-purpose agents against exactly the same task set and publish pass rates and a failure taxonomy.

See [docs/architecture.md](docs/architecture.md), [docs/benchmark.md](docs/benchmark.md), and [docs/roadmap.md](docs/roadmap.md).
