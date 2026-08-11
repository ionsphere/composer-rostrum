# Multi-step agency

Single-edit tasks answer whether an agent can understand one musical instruction and invoke the correct tool. Real production work requires more: later edits depend on the state created by earlier ones, while unrelated material must remain stable.

Composer Rostrum therefore treats **plan depth** as a benchmark dimension.

## Initial families

### Repair → quantize
The agent must inspect an off-chord bass note, choose the nearest valid chord tone, change its pitch, and then quantize only that corrected note. Melody material is protected.

This separates:
- harmony diagnosis;
- choosing a minimal correction;
- targeted timing manipulation;
- preservation of unrelated tracks.

### Duplicate → transform
The agent duplicates an existing phrase into a later arrangement position and transforms only the duplicate. The evaluator checks the *relationship* between source and response rather than an opaque exact project snapshot.

This is a first step toward call-and-response, variation, and arrangement tasks.

### Repair → transpose
The agent repairs a malformed triad and then performs a transformation on the corrected result. The second operation must apply to the state produced by the first operation.

This catches agents that understand both instructions independently but fail to maintain state across the sequence.

## Evaluation philosophy

Multi-step tasks should prefer relational constraints:

- target note belongs to the requested harmony;
- target note lies on the requested grid;
- response is a transformed copy of the call;
- protected tracks or clips are byte-for-byte equivalent in Music IR;
- final harmony remains valid after a later transformation.

A successful run should also expose its trajectory. We can report not only task success but:

- observation count;
- mutation count;
- plan depth;
- redundant or reverted edits;
- protected-state violations;
- whether the agent verified intermediate/final state.

## Next families

1. repair bass against a multi-chord progression;
2. create variations under rhythm-preservation constraints;
3. arrange call/response while preserving source material;
4. sample → transform → resample → place;
5. synth patch → automate → render → revise;
6. vocal timing repair followed by effect/routing changes;
7. mixed MIDI/audio tasks where one edit changes the correct decision for a later edit.

The goal is not long chains for their own sake. A useful task has **dependencies**: solving step N correctly requires understanding the result of step N-1.
