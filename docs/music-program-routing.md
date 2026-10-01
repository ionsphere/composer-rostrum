# Finding a music program before editing

The first agent checkpoint assumed REAPER was already selected. The routing
stage now checks the local executable, automation readiness, and operations
needed by a request before the model edits anything. The model may propose a
program, but code validates its choice against the discovered catalog. When no
connected adapter covers every required operation, the agent returns
`unavailable` with a reason and does not start a model or program session.

Run a read-only discovery check:

```powershell
.venv/Scripts/python.exe scripts/discover_music_programs.py mute_track
.venv/Scripts/python.exe scripts/discover_music_programs.py comp_audio
```

For a benchmark task, provide the canonical operations explicitly. This avoids
mistaking the task's broad `allowed_tools` list for what the user actually
requested. The native runner currently executes routed REAPER tasks:

```powershell
$env:HF_HOME = (Resolve-Path artifacts/first-agent-training).Path + '/hf-cache'
artifacts/train-env/Scripts/python.exe scripts/run_discovered_agent.py examples/tasks/L0-001-set-tempo.json --requires set_tempo --adapter artifacts/first-agent-training/run-routing-001/adapter --output artifacts/routed-tempo-example
```

Audacity is also installed on the validated PC. Its `mod-script-pipe` connection
has not been verified or attached to a native project runner, so discovery
reports it as installed but unusable. The shared `mute_track` intent has
translations to both the REAPER tool API and Audacity's `SelectTracks` then
`SetTrackAudio` commands. The Audacity translation requires a track index read
from the live project; it is not sent to the installed app yet. No broad
Audacity editing capability is claimed. The two documented Audacity commands
come from its [scripting reference](https://manual.audacityteam.org/man/scripting_reference.html),
and its [scripting setup guide](https://manual.audacityteam.org/man/scripting.html)
states that the module must be enabled before external control.

`scripts/export_program_routing.py` appends simulated program catalogs to the
existing REAPER action data. Train phrases and dev phrases are disjoint. Cases
include two capable programs, one capable program, disconnected Audacity, and
no matching program. The `comp_audio` cases must abstain because neither
current adapter claims that operation. A continued LoRA run uses these examples
alongside the original REAPER actions; validation reports routing accuracy
separately from native task success.

The first continuation used 250 LoRA steps on 2,750 usable mixed actions. On
40 held-out routing examples, exact actions rose from 0/40 to 37/40. The three
errors were one attempted selection of disconnected Audacity and two false
abstentions when simulated Audacity was available. The runtime capability check
rejects the unsafe selection. On the same 49 sampled REAPER dev actions, exact
matches rose from 34/49 to 44/49. A routed native tempo task and a native clip
gain task passed. These small samples do not measure full multi-program task
success. The hashes, per-case routing errors, and native outcomes are in the
[validation record](validation/music-program-routing-v1.json).

The continued adapter is packaged locally at
`artifacts/first-agent-training/music-program-routing-adapter-v1.zip` (SHA-256
`8635630cb63cb15d74dbb7b364cfd8d1a13381526f9d3b2806125e01f687898e`).
To reproduce the continuation from the first adapter:

```powershell
.venv/Scripts/python.exe scripts/export_program_routing.py artifacts/first-agent-training/data-final --output artifacts/first-agent-training/data-routing-v3
artifacts/train-env/Scripts/python.exe scripts/train_first_agent.py --data artifacts/first-agent-training/data-routing-v3 --output artifacts/first-agent-training/run-routing-001 --resume-adapter artifacts/first-agent-training/run-002/adapter --max-steps 250 --eval-samples 50 --generation-tokens 256
```

This is the first cross-program slice. The next backend needs a verified
Audacity connection, project readback, command execution, and audio/state evals
before the agent can actually choose Audacity for a live edit. Further programs
should add their own adapter and capability probes rather than borrowing a
REAPER label.
