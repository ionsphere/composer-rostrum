# Audacity native evaluation corpus

`audacity-native-corpus-v1` adds native Audacity 3.7.4 examples to the same
prompt-to-state benchmark shape used for REAPER. Each case contains a public
prompt, public input state, `input.aup3`, and `before.wav`. The private evaluator
adds the expected action, command trace, target state, `target.aup3`, and
`after.wav`. Fixtures are procedurally generated and benchmark-owned.

The first 12 cases cover mute, unmute, solo, track volume, pan, rename, exact-time
split, fade-in, fade-out, peak normalization, a multi-action edit, and an
iterative mix revision. State oracles use Audacity's `GetInfo` track and clip
readback. The audio oracle requires exact PCM identity with the private captured
target, along with frame count, channel count, sample rate, and sample width.
Unrelated tracks and clips must remain present.

Capture requires Audacity with `mod-script-pipe` enabled and a fresh waiting
project window:

```powershell
python scripts/record_audacity_corpus.py --output artifacts/audacity-corpus-v1
python scripts/validate_audacity_corpus.py artifacts/audacity-corpus-v1 --output artifacts/audacity-validation-v1
```

Use `--case CASE_ID` during development to isolate native operations. Capture
explicitly selects the complete project duration and all tracks before export;
Audacity otherwise retains an edit's time and track selection and may export an
empty or partial WAV.

The committed coverage ledger is
[`benchmarks/audacity-feature-coverage-v1.json`](../benchmarks/audacity-feature-coverage-v1.json).
It separates native-verified features from open and hardware-dependent work.
The feature inventory follows the [Audacity manual](https://manual.audacityteam.org/)
and the [scripting command reference](https://manual.audacityteam.org/man/scripting_reference.html).

## Native reopen limitation

Capture-time saves, state readbacks, WAV exports, checksums, and SQLite integrity
checks passed for all 12 cases. A separate loop that called `OpenProject2`,
exported, and then called scripted `Close:` caused Audacity 3.7.4 to terminate
after reopening the first target project and generated a crash dump. The normal
validator therefore stays offline and native reopen remains `partial` in the
coverage ledger. This corpus does not claim restart portability until that path
can be tested without crashing Audacity.

The scripting module exposes a broad command surface, but coverage is earned per
workflow. Noise reduction, cleanup, timing alignment, clip gain, labels,
spectral editing, additional effects, format delivery, macros, and recording are
still open or external in the ledger rather than inferred from command presence.
