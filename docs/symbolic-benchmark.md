# Symbolic musicianship benchmark

Composer Rostrum L1 tests whether an agent can reason about musical structure after it has learned to operate the environment. These tasks intentionally avoid giving the agent the target MIDI pitches when the musical concept itself is what should be inferred.

## Canonical MIDI note shape

A MIDI clip stores notes as stable-ID records:

```json
{
  "id": "n3",
  "pitch": 64,
  "start": 1.5,
  "duration": 0.5,
  "velocity": 92
}
```

Pitch is MIDI 0-127. Time and duration are expressed in project beats. Stable note IDs matter because evaluators need to distinguish a minimal repair from deleting and recreating an entire phrase.

## Initial L1 families

### Transposition
The agent receives an existing phrase and a musical interval in semitones. It must move pitches while preserving timing, duration, velocity, track state, and project state.

### Quantization
The agent must place note starts on a requested beat grid while preserving all non-timing note properties. Later versions should distinguish hard quantization, strength/partial quantization, swing grids, and groove transfer.

### Chord repair
The prompt specifies a target chord symbol, not the desired MIDI pitches. A generated chord contains one corrupted note. The agent must infer the target pitch classes, identify the outlier, and perform exactly one pitch edit.

Example:

```text
Repair clip 'phrase' on track 'keys' so its three simultaneous notes form a D_minor triad.
Exactly one note has the wrong pitch; change only that note's pitch.
```

The evaluator combines semantic harmony (`triad_pitch_classes`) with minimality (`changed_note_count`).

### Scale repair
One note in a phrase is outside a named key. The agent must identify it and move only that note to the nearest valid scale pitch. Evaluation checks scale membership plus minimal edit count rather than requiring a single hidden melody.

## Why this is more useful than exact-answer-only testing

Several musically correct edits can exist. Rostrum should use exact state assertions where the transformation is deterministic, but semantic evaluators where the requested property admits multiple valid realizations. A chord can be voiced in several octaves; an in-key repair may have more than one reasonable pitch. The benchmark should score the property the musician asked for and separately score preservation/minimality.

## Next symbolic families

The next expansions should cover:

- chord inversions and voicing constraints;
- voice-leading with maximum-motion bounds;
- bass-note/chord compatibility;
- rhythmic pattern completion;
- drum-grid reasoning;
- velocity accents and dynamics;
- meter-aware bar placement;
- melody/range constraints;
- call-and-response transformations;
- multi-clip arrangement edits.

These remain intentionally below aesthetic composition. The goal is to establish that an agent can inspect, reason, edit, and verify structured music before asking whether it has taste.
