"""Bounded Responses API tool agent. Optional SDK; no shell or evaluator access."""
from __future__ import annotations
import inspect
import json
import types
import typing
from copy import deepcopy

from .backends.base import BackendError
from .environment import ToolError


class ProviderError(BackendError):
    pass


def _schema(annotation):
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, getattr(types, "UnionType", object())):
        return {"anyOf": [_schema(t) for t in typing.get_args(annotation)]}
    if origin is list:
        return {"type": "array", "items": _schema(typing.get_args(annotation)[0])}
    if origin is dict or annotation in (dict, typing.Any):
        return {"type": "object"}
    return {"type": {str: "string", int: "integer", float: "number", bool: "boolean", type(None): "null"}.get(annotation, "string")}


def tool_schemas(environment):
    tools = []
    for name in sorted(environment.allowed_tools):
        handler = getattr(environment, "_tool_" + name, None)
        if handler is None:
            continue
        # RenderRequest defaults provide a precise schema instead of **kwargs.
        if name == "render":
            from .backends.base import RenderRequest
            handler = RenderRequest
        annotations = typing.get_type_hints(handler)
        properties, required = {}, []
        for key, param in inspect.signature(handler).parameters.items():
            if param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
                continue
            properties[key] = _schema(annotations.get(key, str))
            if param.default is param.empty:
                required.append(key)
        tools.append({"type": "function", "name": name,
            "description": f"{name.replace('_', ' ')}. Musical time is in quarter-note beats; render bounds and audio source ranges are seconds.",
            "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
            "strict": False})
    return tools


class ResponsesAgent:
    def __init__(self, model: str, reasoning_effort: str | None = None, max_turns: int = 20,
                 max_tool_calls: int = 50, max_output_tokens: int = 4096, client=None):
        if not model or min(max_turns, max_tool_calls, max_output_tokens) <= 0:
            raise ValueError("model and positive budgets are required")
        if client is None:
            try:
                from openai import OpenAI
                client = OpenAI(timeout=90, max_retries=0)
            except Exception as exc:
                raise ProviderError("Install the models extra and configure OPENAI_API_KEY") from exc
        self.client, self.model, self.reasoning_effort = client, model, reasoning_effort
        self.max_turns, self.max_tool_calls, self.max_output_tokens = max_turns, max_tool_calls, max_output_tokens
        self.usage = {}
        self.responses = []

    def solve(self, task, environment):
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        self.responses = []
        history = [{"role": "user", "content": task.prompt}]
        calls_used = 0
        tools = tool_schemas(environment)
        for _ in range(self.max_turns):
            options = {"model": self.model, "input": deepcopy(history), "tools": tools,
                "instructions": "You are a music-production agent. Inspect the project, make only requested changes, and verify. Use only supplied tools. Finish when the request is satisfied.",
                "store": False, "include": ["reasoning.encrypted_content"], "parallel_tool_calls": False,
                "max_output_tokens": self.max_output_tokens}
            if self.reasoning_effort:
                options["reasoning"] = {"effort": self.reasoning_effort}
            try:
                response = self.client.responses.create(**options)
            except Exception as exc:
                # SDK exception bodies may contain request details; keep persisted errors bounded.
                raise ProviderError(f"model request failed ({type(exc).__name__})") from exc
            self.responses.append({"id": response.id, "model": response.model, "status": response.status})
            if response.usage:
                for key in self.usage:
                    self.usage[key] += getattr(response.usage, key, 0) or 0
            if response.status != "completed":
                raise ToolError(f"model response was {response.status}")
            history.extend(item.model_dump(exclude_none=True) for item in response.output)
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                return
            for call in calls:
                calls_used += 1
                if calls_used > self.max_tool_calls:
                    raise ToolError("agent tool-call budget exhausted")
                try:
                    arguments = json.loads(call.arguments)
                    if not isinstance(arguments, dict):
                        raise ValueError("tool arguments must be an object")
                    result = environment.call(call.name, **arguments)
                except (ToolError, TypeError, ValueError, KeyError) as exc:
                    result = {"error": f"{type(exc).__name__}: {exc}"}
                history.append({"type": "function_call_output", "call_id": call.call_id,
                                "output": json.dumps(result, allow_nan=False)})
        raise ToolError("agent turn budget exhausted")
