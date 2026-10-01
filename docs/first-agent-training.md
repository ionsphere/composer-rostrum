# First local music-production agent

This experiment fine-tunes a small instruction model to select the next REAPER
tool action. It uses the same prompt and tool-observation boundary as native
corpus evaluation. The model emits one JSON action at a time; the adapter calls
that tool, returns a compact observation, and asks for the next action. `finish`
ends the loop. This is tool-use specialization, not audio generation or a claim
of broad musicianship.

The source is five locally captured, checksum-verified corpora: creation and
revision, item edits, clip gain, rhythm arrangement, and instrument riffs.
`scripts/export_agent_training.py` converts procedural reference trajectories
to next-action examples. It keeps complete chains within train/dev/test, skips
test entirely, and writes no private target project or evaluator into the
model's prompt. It does use the reference trace as the training label. Tool
observations omit worker paths and bulky render metadata, retaining project
state and the audio metrics needed to decide the next action. Every allowed
tool must have a schema; export fails if one is missing.

The first checkpoint uses
[Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct)
with a LoRA adapter. It is a convenient small starting point, not a conclusion
that 0.5B is sufficient. The run records base-model and adapted-model accuracy
on the same fixed dev actions, then can run the adapter through REAPER's private
native evaluator. Teacher-forced next-action accuracy is diagnostic; actual
agent success requires the complete tool loop and final project/audio checks.

On the validated Windows RTX 3080 Ti, use a separate local environment and a
workspace-local Hugging Face cache. The model and adapter stay under ignored
`artifacts/`; only the training code and compact validation report belong in Git.
The first export contained 1,506 train and 501 dev next-action records. The
2,048-token training limit retained 1,470 train actions and excluded 36 long
actions; no test action was exported.

```powershell
py -3.12 -m venv artifacts/train-env
artifacts/train-env/Scripts/python.exe -m pip install --no-cache-dir torch==2.12.0 --index-url https://download.pytorch.org/whl/cu126
artifacts/train-env/Scripts/python.exe -m pip install --no-cache-dir "transformers>=4.51,<5" "peft>=0.17,<1" "accelerate>=1.6,<2" safetensors
artifacts/train-env/Scripts/python.exe -m pip install --no-deps -e .
.venv/Scripts/python.exe scripts/export_agent_training.py artifacts/reaper-corpus-v1-full/dataset artifacts/reaper-item-edits-v1-captured/dataset artifacts/reaper-clip-gain-v1-full/dataset artifacts/reaper-rhythm-arrangement-v1-full/dataset artifacts/instrument-riff-v1-final/dataset --output artifacts/first-agent-training/data
$env:HF_HOME = (Resolve-Path artifacts/first-agent-training).Path + '/hf-cache'
artifacts/train-env/Scripts/python.exe scripts/train_first_agent.py --data artifacts/first-agent-training/data --output artifacts/first-agent-training/run-001 --max-steps 180 --eval-samples 50 --generation-tokens 256
```

For an end-to-end held-out task, use `scripts/eval_local_agent.py` with a dev
sample ID, the same base model, and `--adapter` pointing at the saved adapter.
The native evaluator retains project readback, render evidence, trajectory, and
private audio checks. No training target is staged in the agent workspace.

The corpus has limited source-audio and workflow diversity; related prompts
within a chain share state. Results should therefore be reported with split,
sample count, parse/tool/action accuracy, native task pass rate, infrastructure
failures, model checkpoint, and dataset hashes. A later training round should
add actual model failures and corrected continuations before preference or
online reward training.

The first validated run used a pinned Qwen model revision and 180 LoRA steps.
On 49 fixed dev actions that fit the generation context, exact next actions
rose from 1 for the base model to 34 for the adapter; valid JSON rose from 42
to 49. Three paired native dev tasks (quiet-item gain, its linked loud-item
revision, and an audio split) went from 0/3 to 3/3. Two additional adapted
native dev cases failed: the rhythm edit changed protected guitar items, and
the instrument task invented extra tracks and clips. These selected cases are
diagnostic, not a full native pass-rate estimate. The exact dataset hashes,
checkpoint hash, and per-case outcomes are in
[the validation record](validation/first-local-music-agent-v1.json).

To move this checkpoint to another machine, run
`python scripts/package_first_agent.py artifacts/first-agent-training` after
training and validation. The local archive at
`artifacts/first-agent-training/first-agent-adapter-v1.zip` contains the adapter,
tokenizer, run report, data manifest, and validation record. This run's archive
is 20,290,862 bytes, SHA-256
`1a80b7d655d45295433d0bb29368601f836f915233e67d94b855037e6d49a34b`.
The base Qwen model is downloaded separately at the pinned revision.
