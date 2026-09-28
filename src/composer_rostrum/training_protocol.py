"""Compact, deterministic action protocol for a local music-production agent."""
from __future__ import annotations

import json


SYSTEM = ("You are a REAPER music-production agent. Inspect the project, make only the "
          "requested edits, render when asked, and stop when done. Reply with exactly one "
          "JSON object: {\"tool\":\"tool_name\",\"arguments\":{...}}. Use tool \"finish\" "
          "with empty arguments to stop. Never invent tools or parameters.")


def compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def observation(tool: str, result):
    """Remove worker paths and bulky render metadata from the model's observations."""
    if not isinstance(result, dict):
        return result
    if tool in {"render", "inspect_render", "analyze_render"}:
        metrics = result.get("metrics", result)
        selected = {key: metrics[key] for key in
                    ("duration_seconds", "rms_dbfs", "peak", "silent", "clipped_samples")
                    if key in metrics}
        return {"render_id": result.get("render_id"), "metrics": selected}
    return result


def prompt(task_prompt: str, tools: list[dict], history: list[dict]) -> str:
    lines = ["Task: " + task_prompt, "Available tools: " + compact(tools)]
    for event in history:
        lines.append("Action: " + compact(event["action"]))
        lines.append("Observation: " + compact(event["observation"]))
    lines.append("Next action (JSON only):")
    return "\n".join(lines)


def action(tool: str, arguments: dict) -> dict:
    return {"tool": tool, "arguments": arguments}


def parse_action(text: str, allowed_tools: set[str]) -> dict:
    value = json.loads(text.strip())
    if not isinstance(value, dict) or set(value) != {"tool", "arguments"}:
        raise ValueError("expected one action object with tool and arguments")
    if value["tool"] not in allowed_tools | {"finish"} or not isinstance(value["arguments"], dict):
        raise ValueError("unknown tool or invalid arguments")
    if value["tool"] == "finish" and value["arguments"]:
        raise ValueError("finish takes no arguments")
    return value
