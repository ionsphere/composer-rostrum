# Deterministic ear

`rostrum-ear` compares two uncompressed mono/stereo PCM WAV files without a
model, network call, or subjective listening judgment. It reports exact PCM
identity, duration and active-audio boundaries, RMS/peak level, stereo balance,
autocorrelation pitch (when confidence is high), a 16-band spectral fingerprint,
waveform SNR, and SNR after a fitted gain or onset shift. All measurements and
thresholds are emitted as JSON.

```powershell
python -m composer_rostrum.ear before.wav after.wav --expect '{"kind":"gain_db","value":-6}' --output audio-comparison.json
```

Supported rules are `same`, `different`, `gain_db`, `shift_ms`,
`pitch_semitones`, and `pan_balance_db`. A rule fails when any of its numeric
checks fails; it never chooses a vague overall similarity score. For example,
`gain_db` requires both the requested RMS change (default ±0.2 dB) and a
gain-adjusted waveform SNR of at least 45 dB. `same` requires duration within
1 ms and waveform SNR at least 70 dB. The CLI exits nonzero on a failed rule.

The reference target is private to the evaluator. For fixed-target REAPER corpus
tasks, the exported-input runner checks its checksum, lets the agent edit only
the input project, and then compares the final render to the target WAV. It
records `audio-comparison.json` and adds `reference_audio_match` to the scored
checks. The item-edit corpus also tests its causal waveform relation: a split
preserves audio, and a move relocates the right segment. Feedback tasks retain
RMS-target and improvement checks because multiple gain vectors can satisfy the
same request.

The ear verifies signal properties, not artistic quality or human perception.
Pitch is only reported when a monophonic autocorrelation estimate has adequate
confidence. The spectral fingerprint comes from one central Hann window; it is
a diagnostic for timbre, not a whole-song EQ verdict. Inputs must have equal
sample rate and channel count; the tool does not hide resampling differences.
Analysis is currently bounded to 30 seconds
per WAV so an accidental long render cannot consume unbounded memory.

The [native validation record](validation/deterministic-ear-v1.json) freezes 12
REAPER controls across creation, note edits, fades, pitch/stretch, mixing,
feedback, and item editing. Fixed-target references passed the waveform check;
wrong or no-op edits were rejected by the relevant audio and project oracles.
Authenticated model runs remain separate from these procedural controls.
