# REAPER reference studio v1

Rostrum 0.6 adds a real Python → Lua → REAPER → WAV execution path. The pinned
studio version is REAPER **7.80**; every run records the exact platform build,
bridge version, instrument hash, native project hash, and render settings.
WAV artifacts have both a full-file hash and a PCM hash. REAPER can change
container metadata between renders; audio repeatability is checked on PCM bytes.
The default Python backend checks the version before applying a project.

## Reproduce the acceptance run

Install Python 3.11+ and REAPER 7.80. From the checkout:

```powershell
python -m pip install -e ".[test]"
python scripts/reaper_smoke.py --reaper "C:\Program Files\REAPER (x64)\reaper.exe" --output artifacts/smoke
python scripts/run_daw_suite.py --reaper "C:\Program Files\REAPER (x64)\reaper.exe" --output artifacts/daw-20
```

Each output directory must be new. The smoke test verifies native round-trip,
stable track/item GUIDs, a non-silent four-note render, a one-note edit, changed
audio, saved/reopened state, and identical audio after restarting the worker.
The suite runs twenty tasks: five MIDI, five sample transformations, five mix
edits (gain, pan, send, gain effect), and five RMS feedback tasks.

The same checks are available through pytest:

```powershell
$env:REAPER_EXECUTABLE = "C:\Program Files\REAPER (x64)\reaper.exe"
python -m pytest -m reaper -q
```

Without that variable, native tests are explicitly skipped. Ordinary CI tests
the Lua codec and protocol with a Lua runtime, Python contracts, evaluators,
model tool loop, and benchmark controls. It does not claim to test REAPER.

The checked-in [validation evidence](validation/reaper-7.80.json) records the
actual REAPER 7.80 run, control reports, and restart PCM hashes. Large native
projects/audio remain in the local `artifacts/` directories referenced by that
file. Authenticated model comparisons are explicitly marked as not run.

## Supported portable subset

| Capability | Coverage |
|---|---|
| Global state | Constant tempo (20–300 BPM), meter; key retained as project metadata |
| Tracks | Stable IDs/GUIDs, name, mute, gain, pan |
| MIDI | Stable note IDs, pitch, velocity, position, duration; transpose, quantize, repair, duplicate |
| Audio | Benchmark-owned tone, kick, and plucked-string proxy fixtures; source trim, lossless split, beat-position move, pitch shift, pitch-preserving stretch, linear item fades, item gain on a 0.01 dB grid |
| Instruments | Bundled phase-reset polyphonic sine JSFX, MIDI channel 0 |
| Mix | Audio sends without feedback, deterministic gain JSFX |
| Lifecycle | Independent process/profile, bridge timeout, save/reopen, explicit resume, cleanup |
| Rendering | Immutable integer PCM WAV, mono/stereo, 44.1/48/96 kHz, optional second-based bounds |
| Observations | Duration, rate, channels, peak, RMS/dBFS, silence, clipped sample count |

MIDI times are quarter-note beats and must lie on a 960-ticks/quarter grid.
Native task fixtures are normalized to that grid before execution. Readback
rounds beat/parameter values to nine decimal places; integer/float JSON spelling
does not affect project hashes or preservation. Notes are embedded with ID text
events, and ambiguous/unmapped native state is rejected.

Unsupported graph features and fields fail explicitly. This release does not
claim full REAPER feature coverage: arbitrary sample import, native sampler
mapping, reversal, EQ/compression/sidechains, automation, recording, stems, and
perceptual listening remain outside this reference subset. The in-memory
backend still supports its wider symbolic sample-tool surface.
The [feature coverage ledger](../benchmarks/reaper-feature-coverage-v1.json)
distinguishes native-verified musician intents from partial, open, and
hardware/third-party-dependent workflows. The linked
[item-edit corpus](reaper-corpus.md) adds split and move evaluation samples.
Item gain uses REAPER's native item-volume field with readback, leaving the
track fader and effects untouched. Its [linked clip-gain corpus](reaper-corpus.md)
checks each item's level and waveform before and after the edit.
The [rhythm and arrangement corpus](reaper-corpus.md) adds per-hit kick timing
and pairwise guitar-to-kick alignment; its guitar sound is a deterministic
plucked-string proxy, not a sampled commercial guitar library.

## Isolation and artifacts

The worker uses `-newinst` and a workspace-specific `-cfgfile`. It stages only
Rostrum-owned instruments and fixtures, sets an explicit audio configuration to
avoid first-run device prompts, and requests an empty VST search directory.
REAPER can append system VST3 search paths; the bridge never instantiates those
plugins. The project graph is restricted to the bundled JSFX and fixture audio.
Default launching is hidden on Windows. `--visible` on the smoke script is a
diagnostic option for first-run dialogs; it is not the benchmark control path.

Each native run retains requests, responses, logs, Music IR, `.rpp`, studio
manifest, WAVs, per-render JSON, and `outcome.json`. Model/evaluator files are
not provided to the Lua worker. Python handles semantic validation, while Lua
applies edits to real objects and reads the supported musical fields back from
REAPER. Unchanged clips are left in place; track/item GUIDs survive edits.

The `render` observation precedes `analyze_render`. E3 scoring requires an
analysis of the first render, a subsequent state-changing edit, and a later
render with a closer RMS target. A final render tied to an earlier project
hash fails even if it sounds acceptable. RMS is not LUFS or a perceptual judge.

Render and worker failures are infrastructure failures, separate from semantic,
preservation, audio-target, and feedback failures. A timed-out or malformed
transport is poisoned and must be replaced with a new worker; it never retries
an uncertain mutation. A worker only terminates the process it launched.

## Trial-period coverage plan

Use the remaining evaluation period to close measurable capability gaps before
moving to the next DAW. Do not equate the first passing suite with full coverage.

1. Days 1–10: stabilize E0–E3, repeatability across restarts, malformed input,
   crashes, dialogs, packaging, and the twenty native control tasks.
2. Days 11–25: sampler maps, imported audio, reversal/chopping/fades, effect
   parameter readback, routing/sidechain fixtures, and preservation tests.
   Linear audio fades and linked hybrid creation/revision capture are implemented;
   see the [240-sample native corpus](reaper-corpus.md) and its validation evidence.
3. Days 26–40: automation, tempo maps, region/stem renders, resampling and hybrid
   projects; add task families and failure-injection cases for each capability.
4. Days 41–50: authenticated model comparisons and feedback ablations; distinguish
   tool/environment limitations from musical reasoning failures.
5. Remaining days: freeze the studio manifest, archive native/audio evidence,
   document every unsupported capability, and run backend-conformance fixtures
   against the next DAW adapter. Confirm the actual trial end date in REAPER.

Completion means every selected workflow has positive, negative, preservation,
readback, and real-render evidence. No feature is marked covered merely because
the REAPER API exposes it. No automation is scheduled by this document.

API references: [ReaScript](https://www.reaper.fm/sdk/reascript/reascripthelp.html),
[JSFX MIDI](https://www.reaper.fm/sdk/js/midi.php), and
[JSFX language](https://www.reaper.fm/sdk/js/basiccode.php).
