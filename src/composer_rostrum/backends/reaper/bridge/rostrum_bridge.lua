-- Composer Rostrum REAPER bridge bootstrap.
--
-- Protocol semantics live in docs/reaper-bridge-protocol.md. This first script
-- intentionally implements only in-process command dispatch for ping and
-- capabilities. Workspace transport and persistent polling are the next step.

local PROTOCOL_VERSION = 1
local BRIDGE_VERSION = "0.1-bootstrap"

local function capabilities()
  return {
    protocol = PROTOCOL_VERSION,
    bridge_version = BRIDGE_VERSION,
    reaper_version = reaper.GetAppVersion(),
    capabilities = {
      midi_notes = false,
      audio_clips = false,
      sampler = false,
      native_synth = false,
      native_eq = false,
      compression = false,
      sidechain = false,
      automation = false,
      offline_render = false,
      readback = false,
      headless_or_unattended = false,
    }
  }
end

local handlers = {}

handlers.ping = function(arguments)
  return {
    protocol = PROTOCOL_VERSION,
    bridge_version = BRIDGE_VERSION,
    pong = true,
  }
end

handlers.capabilities = function(arguments)
  return capabilities()
end

local function dispatch(request)
  if request.protocol ~= PROTOCOL_VERSION then
    return nil, "protocol_error", "unsupported protocol version"
  end

  local handler = handlers[request.command]
  if handler == nil then
    return nil, "unsupported_command", "command is not implemented: " .. tostring(request.command)
  end

  local ok, result = pcall(handler, request.arguments or {})
  if not ok then
    return nil, "reaper_error", tostring(result)
  end
  return result, nil, nil
end

-- Export a tiny global for REAPER's interactive ReaScript console/tests. The
-- persistent file/socket transport will invoke the same dispatcher later.
RostrumBridge = {
  protocol = PROTOCOL_VERSION,
  version = BRIDGE_VERSION,
  dispatch = dispatch,
  capabilities = capabilities,
}

reaper.ShowConsoleMsg("Composer Rostrum bridge bootstrap loaded (protocol 1)\n")
