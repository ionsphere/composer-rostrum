# REAPER creation and revision corpus

`reaper-chains-v1` contains 40 independent composition chains and 240 prompts:
40 creation requests and 200 revisions of existing native projects. Every chain
has seven saved states (including its empty input), six reference renders, and
six tool trajectories. These are procedural reference demonstrations, not human
performances or authenticated model results.

| Stage | Request | Evaluation |
|---|---|---|
| Create | Build a precisely specified MIDI/audio project from an empty arrangement and a provided asset | Native track/clip/note state, ordering, tempo, non-silent audio |
| Transpose | Change all phrase pitches while preserving note identity and rhythm | Exact pitch changes, protected state, stable native GUIDs |
| Trim and fades | Select a source range and set linear item fades | Native offsets, item length, fade lengths, preservation |
| Pitch and stretch | Change sample pitch and pitch-preserving playback duration | Native take pitch/rate and source range; fades stay in seconds |
| Mix | Pan, add an audio send, and insert a gain effect | Native parameters and routing plus preservation |
| Feedback | Measure the mix and revise source gains to meet an RMS target | Fresh final render, tolerance, observation → edit → render, improved error |

Tempo, note pitches, rhythmic positions, velocities, trims, fades, pitch/stretch
values, mix parameters and RMS targets vary deterministically. This measures
parameter generalization within six workflows; it is not a held-out workflow or
musical-style benchmark. The single owned audio fixture and sine instrument do
not stand in for broad real-world sound-library coverage.

## Capture before the evaluation period ends

```powershell
python -m pip install -e ".[test]"
python -m composer_rostrum.corpus_capture --reaper "C:\Program Files\REAPER (x64)\reaper.exe" --output artifacts/reaper-corpus-v1-full --chains 40 --workers 4
```

Use a Python 3.11+ interpreter. On the validation workstation, the checkout's
`.venv\Scripts\python.exe` was used because `python` on `PATH` is Python 3.9.
The output must be new. `--workers` accepts 1–4 isolated REAPER processes.
Start with `--chains 1 --workers 1` for a small pilot. If a capture fails, use the
same options plus `--resume`: complete chains are checksum-checked and reopened
at a new path; incomplete chains run again in fresh workspaces. A timed-out
worker is never reused. Abandoned attempts remain as local diagnostic evidence
and are excluded from the final archive. Any failed chain prevents publication
of a success report/archive.

The capture produces `dataset/`, `reaper-chains-v1.zip`, and `archive.json` with
the archive's SHA-256. Keep the ZIP and checksum together in durable storage
before moving away from REAPER. The archive includes the actual `.rpp` files,
source WAVs, rendered WAVs, bundled JSFX, prompts, state JSON, evaluation targets,
and traces. Open `dataset/catalog.html` to search/filter prompts, open before/after
projects, and play their audio locally. Audio referenced by feedback traces is
also packaged; trace paths are relative to the dataset root. It does not include
REAPER or extend its evaluation period.

The checked-in [sample index](../benchmarks/reaper-chains-v1.json) freezes prompts
and task hashes. [Validation evidence](validation/reaper-chains-v1.json) records
native results and archive checksums. Large audio/native archives stay under the
local `artifacts/` directory, which is excluded from Git; the PR alone is not a
backup of those files.

## Dataset layout and evaluation boundary

```text
dataset/
  samples.jsonl             # index for the harness
  inputs/<sample>.json      # prompt, allowed tools, input-state reference
  private/<sample>.json     # private task/oracles, target reference, edit trace
  states/<chain-attempt>/<stage>/
    project.rpp
    project.music-ir.json
    state.json             # file hashes, native IDs, render metrics
    assets/tone.wav
    render.wav             # absent only from empty input states
  Effects/Rostrum/          # bundled deterministic instrument and gain effect
  checksums.json
  validation.json
```

Split by whole chain: 24 train, 8 dev, 8 test (144/48/48 prompt/state pairs).
Never train on an earlier turn of a held-out chain: its output is the next turn's
input. Expose only the selected input JSON and state to an agent. Targets, later
states, reference traces, generator, and global inventories remain outside its
observation boundary. The archive itself is an evaluator artifact, not an agent
workspace. For reference training, pair each input with its private target and
trajectory only within the training split.

Creation and fixed edits have exact canonical-state targets. Feedback accepts
multiple gain solutions satisfying audio and preservation constraints; its
reference target is an example, not the only permitted gain vector. All edits
must preserve pre-existing native track/item GUIDs during reference capture.

Every captured state is saved by REAPER. Export changes only the worker path
prefix to relative paths; it does not synthesize RPP musical chunks. Each chain's
final state is reopened in another directory in a fresh process without
rematerializing it; canonical state, GUIDs and rendered PCM must match. This is
40 final-state relocation checks, not a claim that all 280 states were separately
restarted. Creation, transposition, fades and feedback also have independent
native evaluation-runner control checks.

The archive also retains the exact Lua/JSFX source hashes used by each capture.
Regenerating a chain can produce different native GUIDs, timestamps and container
hashes; task hashes, canonical Music IR and PCM are the relevant reproducibility
checks. File checksums identify the specific frozen capture being evaluated.

To open a project manually, install `Effects/Rostrum` in the REAPER resource
directory's `Effects` folder and open its `project.rpp`. Keep the state directory
and its `assets` folder together. The Python runner stages JSFX automatically in
an isolated profile.

## Run an agent on a captured native input

Configure `OPENAI_API_KEY` locally and select a model available to your account:

```powershell
python -m pip install -e ".[models]"
python -m composer_rostrum.corpus_eval artifacts/reaper-corpus-v1-full/dataset chain-0000-02-trim-fades --reaper "C:\Program Files\REAPER (x64)\reaper.exe" --model YOUR_MODEL_ID --output artifacts/model-corpus-sample
```

The runner verifies input hashes, copies the input `.rpp` and assets, opens that
native state, then gives the agent only the prompt and permitted tools. It does
not materialize the reference target. The output includes evaluation results,
trajectory, usage, native project, and renders. Model runs remain unperformed
until provider credentials and models are configured.

Fixed-target samples also receive a private
[deterministic-ear comparison](deterministic-ear.md) against their reference WAV.
The scorer writes `audio-comparison.json` and requires the expected PCM to be
present, so a correct project graph with a partial or silent render cannot pass.
Feedback samples retain goal-based loudness scoring because more than one mix
can meet the requested RMS target.

Reference and negative evaluation-runner checks:

```powershell
python scripts/verify_corpus_controls.py artifacts/reaper-corpus-v1-full/dataset --reaper "C:\Program Files\REAPER (x64)\reaper.exe" --output artifacts/corpus-controls
python -m pytest -q --junitxml artifacts/corpus-unit-tests.xml
# Run the opt-in test with REAPER_EXECUTABLE configured:
python -m pytest tests/test_reaper_live.py -k linear_fades -q --junitxml artifacts/fade-native-test.xml
python scripts/record_corpus_validation.py artifacts/reaper-corpus-v1-full --controls artifacts/corpus-controls/summary.json --unit-results artifacts/corpus-unit-tests.xml --fade-results artifacts/fade-native-test.xml
```

## Remaining coverage

The [versioned REAPER feature ledger](../benchmarks/reaper-feature-coverage-v1.json)
turns the broad UI goal into musician intents across project setup, tracks,
recording, MIDI, audio editing, routing, effects, automation, rendering, media,
and customization. `native_verified` requires prompt, actual `.rpp` before/after,
semantic and preservation checks, render evidence, and a relocated reopen. `partial`
and `open` cannot be counted as coverage. Hardware and arbitrary third-party
plug-ins have an explicit `external` status until a reproducible fixture exists.
The ledger is a growing task ontology, not a claim that every REAPER action or
extension is already represented. Each new feature needs positive and wrong-edit
controls, native property readback, output evidence suited to the intent, and a
restart check. Some intents preserve PCM by design, such as a lossless split;
their output oracle should check equality rather than demand a changed waveform.

`reaper-item-edits-v1` adds linked split and move revisions to a separate corpus
without changing frozen `reaper-chains-v1` samples. Its split step checks two
adjacent native items and exact source ranges; its move step checks a beat-position
change and a different render. The relocated final state verifies project state,
stable GUIDs, and PCM. Explicit zero fades prevent REAPER's default 10 ms edge
fades from changing a lossless split. On relocation, a 24-bit render may differ
by one least-significant bit in at most 0.01% of samples; the verifier records
exact equality separately and rejects anything beyond that narrow threshold.
Capture with:

```powershell
.venv\Scripts\python.exe -m composer_rostrum.corpus_capture --suite item-edits --reaper "C:\Program Files\REAPER (x64)\reaper.exe" --output artifacts/reaper-item-edits-v1-captured --chains 20 --seed 20260924 --workers 2
.venv\Scripts\python.exe scripts/record_item_edit_validation.py artifacts/reaper-item-edits-v1-captured
```

The checked-in [item-edit prompt index](../benchmarks/reaper-item-edits-v1.json)
and [native validation record](validation/reaper-item-edits-v1.json) freeze the
40 prompts, 60 rendered native states, split waveform checks, moved-segment
checks, and 20 relocation checks. The full WAV/RPP archive stays in the ignored
`artifacts/` folder. Exported-input reference, no-op, and wrong-move controls
can be rerun with `scripts/verify_item_edit_controls.py`.

Next capture families should cover owned imported PCM audio, chopping/reversal,
sampler maps, effect parameter changes, automation and tempo maps, then stem and
region renders. Each family needs positive, wrong-edit, preservation, readback,
render and reopen cases before being marked covered. This corpus closes the
linked prompt/state dataset gap and adds linear audio fades; it does not close
the remaining REAPER roadmap.

Native fade fields are documented in the official
[ReaScript API](https://www.reaper.fm/sdk/reascript/reascripthelp.html#SetMediaItemInfo_Value).
