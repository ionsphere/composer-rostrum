# Creator Workflow Coverage

Composer Rostrum should not benchmark only conservatory-style composition or large-studio production. A major target is the **small independent creator**: one person, one DAW, a small set of instruments/effects, and a workflow that freely mixes MIDI, synthesis, samples, recorded audio, resampling, and automation.

The creator references below are used as **workflow archetypes**, not imitation targets. The benchmark should never require reproducing a living artist's style, catalog, exact preset, or proprietary project. Where exact tools are not publicly verified, we benchmark the observable production capability rather than guessing plugin names.

## Why this matters

An agent that can write correct chords but cannot chop a phone recording, stretch it to tempo, map slices, layer it under a synth, automate an effect, and bounce/resample the result is not yet an autonomous contemporary music maker.

For these workflows, audio is not merely the final render. **Audio clips are compositional objects.** The Music IR and tool surface must therefore treat recorded/found/generated samples as peers of MIDI notes.

## Archetype A — found-sound / resampling producer

Reference: Venjent's publicly visible workflow often starts from an everyday sound and develops musical material through sampling and transformation.

Benchmark capabilities:

- import a short audio recording;
- inspect waveform duration, transients, pitch and tempo cues;
- trim and crop useful regions;
- split/chop at explicit or detected points;
- map slices into a sampler;
- reorder slices rhythmically;
- time-stretch with and without pitch preservation;
- pitch-shift by semitones/cents;
- reverse selected regions;
- loop with clean boundaries;
- apply fades/crossfades;
- layer a transient from one source with the body/tail of another;
- process through filters, EQ, distortion/saturation, compression, delay and reverb;
- automate effect parameters;
- bounce/freeze/resample a processing chain and continue editing the resulting audio;
- derive drums, bass, melody or texture from a non-musical source;
- preserve recognizable rhythmic intent while radically changing timbre.

Representative tasks:

> Turn these four machine noises into a four-on-the-floor percussion loop at 128 BPM. Use only the supplied recordings.

> The first slice has a click at its loop boundary. Repair the loop without changing its perceived rhythm or pitch.

> Use this door-closing sample as the transient layer for the existing snare while preserving the snare's original tail.

> Resample this processed vocal chop, reverse only its final quarter, and place it as the pickup into bar 17.

## Archetype B — synth + sequencer + lightweight arrangement

References: independent synth-pop / electronic creators such as Stereopolina, whose project is publicly described as self-created and self-recorded, spanning synth-pop, new wave, disco/electroclash and related electronic styles.

Benchmark capabilities:

- create and edit MIDI patterns;
- choose or configure a subtractive/FM/wavetable synth by semantic parameters;
- program bass, pads, leads and arpeggios;
- construct drum-machine patterns;
- layer synth and sample instruments;
- voice chords within register constraints;
- automate filter cutoff, resonance, envelope, panning and sends;
- make section-level arrangement edits;
- route tracks to buses;
- perform basic mix balancing without a dedicated engineer;
- record or import vocals and integrate them with electronic instrumentation.

The benchmark should include projects that are realistically small: e.g. 6–20 tracks and a handful of stock-equivalent processors rather than assuming 100-track professional sessions.

## Archetype C — vocal-led electronic creator

References: Angel Vox and similar independent electronic/vocal creators.

Exact tool inventories should be treated as unverified unless documented from primary/public sources. The relevant archetype is a creator who combines vocals with software instruments, samples and effects in one DAW.

Benchmark capabilities:

- comp/trim vocal takes;
- align phrases to musical time without flattening expression;
- pitch-shift or formant-shift selected phrases;
- create vocal chops as playable material;
- duplicate and layer harmonies;
- automate delay/reverb throws;
- duck backing elements around vocal phrases;
- use vocal audio as both foreground performance and transformed texture;
- preserve intelligibility while changing timbre;
- render alternate instrumental / vocal / stem versions.

## Archetype D — hybrid DIY producer

References: Loolacoma and other small creators whose released work mixes software tools rather than following a single-instrument or single-synthesis workflow.

This bucket exists specifically to prevent overfitting Rostrum to MIDI-only composition. Benchmark projects should freely combine:

- MIDI instruments;
- one-shot samples;
- longer audio clips;
- recorded voice/instruments/foley;
- sampler instruments;
- plugin chains;
- sends/returns;
- automation;
- resampled/bounced intermediates.

The agent must reason across representations. For example, the correct solution to a musical problem may be to edit MIDI, manipulate audio, change synthesis, or alter routing depending on the project state.

## Required Music IR additions

To support these workflows, Music IR needs at least:

```text
AudioAsset
  id
  provenance/license
  sample_rate/channels
  duration
  content_hash

AudioClip
  asset_id
  source_start/source_end
  timeline_start/duration
  gain/pan
  playback_rate
  pitch_shift
  preserve_pitch
  reverse
  fades
  warp markers

Sampler
  mappings: note/range -> asset slice
  root note
  loop region
  envelope

EffectInstance
  type/plugin capability
  parameters
  bypass

AutomationLane
  target
  points/curves

RenderAsset
  source graph hash
  render settings
  provenance chain
```

The canonical IR should describe **capabilities**, not require a specific commercial plugin. A benchmark can ask for a low-pass filter or sampler even if one backend implements it with REAPER stock devices and another with FL Studio devices.

## Required environment tools

Near-term tool surface should grow to include:

```text
import_audio
inspect_audio
create_audio_clip
trim_clip
split_clip
move_clip
duplicate_clip
reverse_clip
set_clip_gain
set_clip_pitch
stretch_clip
set_fades
create_sampler
map_sample_slice
add_effect
set_effect_parameter
add_automation
render_region
resample_region
replace_with_render
```

Later perceptual tools can expose measurements without handing the answer to the agent:

```text
detect_transients
estimate_pitch
estimate_tempo
measure_loudness
measure_spectrum
compare_audio
```

## Benchmark families to add

Rostrum should eventually include dedicated families for:

1. audio trimming and placement;
2. transient-aware chopping;
3. sample-to-grid timing;
4. pitch/time transformation;
5. loop repair and crossfades;
6. sampler mapping;
7. rhythmic rearrangement of slices;
8. sample layering;
9. FX-chain construction;
10. parameter automation;
11. bounce/resample/edit loops;
12. vocal-chop construction;
13. vocal comp/timing tasks;
14. hybrid MIDI + audio arrangement;
15. provenance-preserving sample substitution.

## Evaluation strategy

Many of these tasks remain objectively testable before aesthetics enter the picture.

Examples:

- exact source region and timeline placement;
- slice count and boundaries within transient tolerance;
- target duration/BPM after stretch;
- target pitch interval;
- no unintended changes outside a requested clip;
- loop discontinuity energy below threshold;
- required routing/effect graph present;
- automation target and range correct;
- resampled asset derived only from allowed source assets;
- preserved protected tracks/assets bit-for-bit or semantically unchanged.

For open transformations, score several dimensions separately: structural correctness, source/provenance compliance, rhythmic preservation, audio quality, and perceptual suitability.

## Dataset/provenance rule

Sample manipulation makes provenance especially important. Benchmark assets should be procedural, self-recorded for Rostrum, public-domain, or explicitly licensed for redistribution and transformation. Every derived render should retain a provenance graph back to its input assets and processing actions.

This is useful scientifically as well as legally: it lets us ask whether the agent truly created a transformation from the supplied material rather than silently substituting some unrelated learned/generated audio.
