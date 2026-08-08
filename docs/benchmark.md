# Benchmark Design

## Benchmark unit

A Rostrum instance is intentionally shaped like a software-agent benchmark instance:

```text
(initial project, request, tools, evaluators) -> agent trajectory -> final project -> score
```

The preferred task is an **edit of an existing project**, not unconstrained blank-page generation.

## Levels

### L0 — mechanics
Exact state manipulation: tempo, mute/solo, naming, duplication, arrangement moves, routing basics. Mostly binary evaluation.

### L1 — musical syntax
Harmony, scales, rhythm, meter, voicing, voice-leading, quantization, instrumentation constraints. Property-based symbolic evaluation.

### L2 — production
Masking, level balance, dynamics, routing, effects, transient control, stereo placement, sample manipulation, resampling, and hybrid MIDI/audio workflows. Multiple valid solutions; evaluate requested outcome plus preservation.

### L3 — perceptual editing
Humanization, feel, tension, density, clarity, similarity/preservation. Requires hybrid structural and perceptual metrics.

### L4 — composition
Open musical decisions under explicit constraints. No single oracle; use suites of constraint, critic, preference, and human evaluators.

## Workflow coverage

Rostrum must cover not only notation-first composition or large-studio mixing, but also the workflow of a **small independent creator working inside one DAW**. These projects commonly mix MIDI, synths, samples, recorded audio, vocal takes, effects, automation, and repeated bounce/resample steps.

Audio must therefore be a first-class compositional object in the benchmark, not just the final render.

Creator references such as Venjent, Loolacoma, Angel Vox, and Стереополина are used as workflow archetypes, not as style-imitation targets. We benchmark observable capabilities and do not guess unverified plugin inventories. See [creator-workflows.md](creator-workflows.md).

## Task families for Rostrum-100

Initial candidate families:

1. tempo/meter manipulation
2. track state and naming
3. clip/bar movement and duplication
4. note transposition
5. quantization and timing
6. velocity/dynamics
7. chord construction/correction
8. scale/key conformance
9. simple arrangement repair
10. routing and bus creation
11. basic EQ constraints
12. compression/sidechain setup
13. gain staging/clipping repair
14. preservation-focused edits
15. multi-step combinations

Rostrum-100 should bias toward deterministic tasks. Difficulty should come from state size, ambiguity, multi-step dependencies, and preservation requirements—not from subjective taste.

## Audio/sample benchmark track

After the deterministic symbolic/mechanics core, add a parallel benchmark track for modern creator workflows:

1. audio trim/place/move
2. transient-aware chopping
3. time-stretch and pitch-shift
4. loop repair and crossfades
5. sampler mapping
6. sample-slice rearrangement
7. sample layering
8. effect-chain construction
9. automation
10. bounce/resample/re-edit
11. vocal chops and vocal timing
12. hybrid MIDI + audio arrangement

These should begin with synthetic/self-recorded benchmark assets so most tasks remain executable and provenance-clean.

## Procedural generation

A generator should be reproducible from a seed:

```text
seed -> valid project -> mutation/transformation -> prompt -> hidden oracle/evaluators
```

Examples:
- generate a groove, shift one bass entrance early, ask the agent to repair it;
- generate a progression, corrupt one chord tone, ask for a theory-correct repair;
- generate routing, remove a sidechain edge, ask for kick-triggered bass compression;
- generate a balanced project, introduce clipping, ask for repair while preserving integrated loudness within tolerance;
- generate a set of synthetic/recorded transients, ask the agent to chop and map them into a rhythm;
- create a deliberately bad loop boundary, ask the agent to remove the click without altering musical timing;
- provide a found-sound clip and require a specific rhythmic/pitched transformation while using no outside audio.

Train and held-out benchmark splits must separate generator seeds and ideally generator templates so agents cannot pass by memorizing surface forms.

## Scoring

Prefer explicit dimensions over a single opaque judge score:

- **instruction correctness** — requested state/outcome achieved;
- **preservation** — unrelated state unchanged;
- **musical validity** — symbolic constraints hold;
- **audio outcome** — measurable rendered-audio target improved/met;
- **source/provenance compliance** — transformed material derives only from allowed assets where required;
- **efficiency** — optional secondary metric for tool calls/tokens/time;
- **aesthetic preference** — only where inherently required.

A task may declare hard gates. For example, a beautiful result that modifies a protected vocal track can still fail.

## Contamination and provenance

Every task should record how source material was created and under what rights it is distributed. The benchmark core should prefer procedural material. Public-domain and explicitly licensed material can broaden realism later.

For sample-manipulation tasks, derived assets should retain provenance back to source asset IDs and processing actions.

The benchmark should never assume that changing output format from audio to MIDI removes composition copyright concerns. Provenance is a first-class dataset field.

## Validation

Before calling a task benchmark-ready:

1. reference solver passes;
2. intentionally wrong solver fails;
3. evaluator is invariant to irrelevant serialization/order differences;
4. preservation checks catch over-editing;
5. task is reproducible from source assets/seed;
6. no evaluator secret is exposed to the agent;
7. at least one human reviews that the natural-language request matches the test.

## Reporting

Publish aggregate score plus breakdown by level, family, workflow archetype, and failure class. Record trajectories so failures can be categorized as perception/state-reading, planning, tool use, musical reasoning, audio judgement, source/provenance handling, or verification failures.
