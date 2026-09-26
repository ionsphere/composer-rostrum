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

Four region-level rules are available for production stages. They require equal
sample rate, channel count, and duration for the before/after renders. Time
ranges are milliseconds; each rule returns measurements and named checks.

| Rule | Intent and evidence | Required fields |
| --- | --- | --- |
| `comp` | Each segment matches its declared source recording in its interior; joins have a small sample discontinuity relative to nearby level. | `segments`: `{start_ms,end_ms,source,source_start_ms?}` |
| `timing` | A one-to-one set of detected attacks lands on expected times; optional protected regions retain their waveform. | `expected_ms`, optional `protected_regions`: `[[start_ms,end_ms], ...]` |
| `noise_cleanup` | Noise-only windows lose level while signal windows retain level and waveform shape. | `noise_windows`, `signal_windows` |
| `clip_gain` | Each clip window reaches its RMS target, preserves its waveform shape, and the output does not clip. | `clips`: `{start_ms,end_ms,target_rms_dbfs}` |

For example, a noise cleanup rule can be run as:

```powershell
python -m composer_rostrum.ear before.wav after.wav --expect '{"kind":"noise_cleanup","noise_windows":[[0,200],[800,1000]],"signal_windows":[[300,700]],"min_reduction_db":12}'
```

The default comp identity threshold is 30 dB fitted waveform SNR, with at
least 0.5 positive fitted gain. Its join limit is -12 dB relative to local RMS.
Timing uses 2 ms energy windows, an attack floor of -35 dBFS, an 8 dB rise,
and a default ±5 ms target tolerance. Noise cleanup requires at least 12 dB
noise reduction, at most 1 dB signal loss, and 25 dB signal-window fitted SNR.
Clip gain uses ±0.5 dB RMS target tolerance, 35 dB fitted shape SNR, and a
-0.1 dBFS output peak ceiling. These are explicit, overridable rule parameters;
calibrate them against each corpus item and render chain rather than treating
them as perceptual constants.

Audio cannot prove which REAPER take was selected, whether gain was applied
before effects, or whether source items were preserved. Those require project
state checks alongside these signal checks. A join jump is a cheap click proxy,
not a perceptual click detector; a transient grid is only meaningful for known
percussive source material. The tests include positive controls and wrong-take,
click, missing-transient, muted-cleanup, and global-gain negative controls.

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
