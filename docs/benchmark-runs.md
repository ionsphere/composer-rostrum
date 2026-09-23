# Reproducible Rostrum-120 and model comparisons

Rostrum-120 v1 freezes 120 tasks across twelve families: tempo, key, meter,
mute, gain, transpose, quantize, chord repair, scale repair, repair→quantize,
duplicate→transform, and repair→transpose. Every family has six train, two dev,
and two test tasks. Semantic project/prompt fingerprints are unique across all
splits. These are deterministic development/held-out splits, not a claim of
resistance to contamination from the public generator.

```sh
python -m pip install -e '.[test]'
rostrum-benchmark artifacts/rostrum-120 --controls
```

The manifest records generator version, seed, split, task content hash and
semantic fingerprint. `oracles/` contains deterministic reference states and
mutation trajectories for debugging. Those files and task evaluators stay on
the evaluation side of the boundary. The model receives only the producer
prompt, permitted tool schemas and tool observations. The reference agent also
receives a copy of the task with evaluators removed.

Controls deliberately test three different properties:

- Reference: all 120 tasks must be solvable through the declared tools.
- No-op: initial projects must not already satisfy the request.
- Damaging: satisfying the request while changing protected state must fail.

These controls are **not general-purpose model comparisons**. Oracles include
allowed mutation paths, and preservation checks reject every other delta.
The repaired-triad evaluator checks the actual requested octave, identity,
timing and velocity rather than only checking pitch classes.

## Actual model runs

Install the optional SDK, configure `OPENAI_API_KEY` in your local environment,
and copy `examples/model-comparison.json` to a local configuration file. Replace
each placeholder with an accessible model ID. Three models or three supported
reasoning settings on one model are both valid configurations. The example is
not a selection of available models and is not runnable until edited.

```sh
python -m pip install -e '.[models]'
rostrum-compare artifacts/rostrum-120 path/to/models.json artifacts/comparison --split test
```

The comparison runner verifies every task against the frozen manifest and uses
the same ordered split for every configuration. It records model response IDs,
resolved model IDs, token usage, tool calls, elapsed time, per-task trajectories,
scores and grouped reports by level/family/execution level/failure class. It
does not estimate dollar costs from unpinned prices. API requests use explicit
turn, tool-call and output-token limits, no automatic retries, and `store=false`.
Function-call outputs and reasoning items are preserved between turns.

Reports retain infrastructure failure counts and exclude them from the agent
pass-rate denominator. A score without the task count and infrastructure count
is incomplete. Provider errors are infrastructure failures; invalid model tool
arguments are observations that the model may recover from within its budget.

The current comparison CLI runs the symbolic split with the in-memory backend.
The `ResponsesAgent` can also be passed to `run_task` with a REAPER backend and
one of the native tasks. Its audio feedback consists of structured measurements;
it does not claim native audio perception.

No API credentials or model choices are bundled. A completed three-configuration
model report requires an authenticated run; mock SDK tests validate integration
behavior only. See the official [function-calling guide](https://developers.openai.com/api/docs/guides/function-calling)
for the API protocol used here.
