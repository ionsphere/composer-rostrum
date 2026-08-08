# External Sample Discovery (future)

Composer Rostrum should eventually test whether an agent can discover sounds outside the initial project, but discovery must be separated from import and use.

## Proposed capability boundary

```text
search_samples(query, constraints) -> candidates
inspect_sample(candidate_id) -> metadata + preview analysis
license_sample(candidate_id) -> acquired asset + rights receipt
import_asset(asset_id) -> project asset
```

`search_samples` is discovery only. A candidate must not become usable project material until its rights state is explicit.

## Candidate metadata

Every externally discovered candidate should carry, where available:

- provider and canonical source URI;
- creator/uploader;
- content hash after acquisition;
- duration, format, sample rate, channels;
- tags and machine/audio analysis;
- license identifier and license text/URL snapshot;
- attribution requirements;
- whether commercial use, modification, redistribution, and model-training use are permitted;
- acquisition timestamp;
- evidence/receipt sufficient to audit why the harness considered the use permissible.

If rights cannot be resolved, the benchmark should represent the candidate as `rights_verified: false` and prevent normal import unless the task explicitly tests rights reasoning.

## Why this belongs in the benchmark

A human producer does not work from a sealed sample folder. They record sounds, browse libraries, buy packs, use public-domain archives, commission recordings, and sometimes reject a perfect sound because its rights are wrong. A capable production agent should eventually make the same distinction.

This creates future task families such as:

- find a legally reusable metallic impact and turn it into a snare layer;
- find three candidate ambience recordings and select one matching a spectral/duration constraint;
- reject a musically ideal sample because commercial modification is not permitted;
- prefer an already-owned/local asset over downloading a near-duplicate;
- acquire a licensed sample and preserve its attribution through several derived renders.

## Benchmark safety and reproducibility

Public benchmark runs should not depend on mutable web search results. External-search tasks should use one of:

1. a frozen benchmark search index mirroring rights-cleared assets;
2. recorded provider responses plus downloadable immutable fixtures;
3. a live-search evaluation track reported separately from deterministic benchmark scores.

The canonical task artifact should record query, provider result IDs, acquisition receipt, hashes, and provenance graph. This keeps the core benchmark reproducible while still allowing research on open-world musical agency.
