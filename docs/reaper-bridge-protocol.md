# REAPER Bridge Protocol v1

The REAPER backend uses a small request/response protocol between the Python worker and a persistent Lua ReaScript running inside REAPER.

## Goals

- stable semantic operations instead of GUI coordinates;
- inspectable transport for benchmark debugging;
- explicit version/capability handshake;
- request IDs so every native operation can be tied to the Rostrum trajectory;
- no benchmark evaluator/oracle data inside REAPER;
- transport can later move from files to localhost JSON-lines without changing command semantics.

## Initial transport

The bootstrap transport is workspace files:

```text
workspace/
  requests/
    000001.json
  responses/
    000001.json
  logs/
  renders/
  project.music-ir.json
  project.rpp
  reaper-worker.json
```

The Python worker writes requests atomically (temporary file then rename). The Lua bridge processes monotonically increasing request IDs and writes exactly one response per request.

## Request envelope

```json
{
  "protocol": 1,
  "id": "000001",
  "command": "ping",
  "arguments": {}
}
```

## Response envelope

Success:

```json
{
  "protocol": 1,
  "id": "000001",
  "ok": true,
  "result": {},
  "error": null
}
```

Failure:

```json
{
  "protocol": 1,
  "id": "000001",
  "ok": false,
  "result": null,
  "error": {
    "kind": "invalid_argument",
    "message": "..."
  }
}
```

## Command rollout

### Bootstrap commands

1. `ping`
2. `capabilities`
3. `project_info`
4. `save_project`

### E0/E1 MIDI commands

5. `list_tracks`
6. `list_items`
7. `list_midi_notes`
8. `set_tempo`
9. `set_note_pitch`
10. `set_note_start`
11. `insert_midi_note`
12. `delete_midi_note`
13. `duplicate_item`

### E2 render commands

14. `configure_render`
15. `render_project`
16. `render_status`

### Later production commands

- audio item trim/move/stretch/pitch/reverse;
- FX insert/remove/parameter changes;
- routing/sidechain;
- automation envelopes;
- sampler operations.

## Identifier mapping

Rostrum IDs must not rely on ephemeral REAPER object pointers. The bridge should persist stable IDs in native metadata/ext-state where possible and return both:

```json
{
  "rostrum_id": "bass",
  "native_id": "...",
  "kind": "track"
}
```

Readback must preserve Rostrum IDs across save/reopen cycles.

## Handshake

`capabilities` returns both protocol and worker environment information:

```json
{
  "protocol": 1,
  "bridge_version": "0.1",
  "reaper_version": "...",
  "capabilities": {
    "midi_notes": true,
    "readback": true,
    "offline_render": false
  }
}
```

The Python backend validates this before allowing a task to start. Task capability requirements are checked against the live handshake, not merely against what the backend hopes to support.

## Failure classes

The worker should distinguish:

- `protocol_error`
- `unsupported_command`
- `invalid_argument`
- `native_object_missing`
- `reaper_error`
- `render_error`
- `timeout`
- `dialog_blocked`
- `plugin_missing`

These are infrastructure/native-execution diagnostics and should not be flattened into evaluator failures.

## First integration target

The first real bridge test is deliberately small:

1. start REAPER with an isolated worker workspace;
2. receive a successful handshake;
3. open/materialize one MIDI project;
4. inspect one note;
5. change its pitch through `set_note_pitch`;
6. save;
7. reopen/read back;
8. verify the Music IR semantic delta.

Only after that passes do we add the first genuine WAV render.