import json
from copy import deepcopy
from types import SimpleNamespace
import pytest
from composer_rostrum.model_agent import ResponsesAgent, tool_schemas, ProviderError
from composer_rostrum.environment import MusicEnvironment, ToolError
from composer_rostrum.generator import generate_task
from composer_rostrum.runner import run_task


class Item(SimpleNamespace):
    def model_dump(self, **kwargs):
        return self.__dict__.copy()


def response(*calls):
    return SimpleNamespace(id="response-id", model="test-model", status="completed",
        output=[Item(type="function_call", name=name, arguments=json.dumps(args), call_id=str(i)) for i,(name,args) in enumerate(calls)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15))


class FakeClient:
    def __init__(self, responses):
        self.results = iter(responses)
        self.requests = []
        self.responses = self
    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        return next(self.results)


def test_agent_uses_observations_and_never_receives_oracle():
    task = generate_task(0, 12)
    target = task.evaluators[0]["equals"]
    client = FakeClient([response(("inspect_project", {})), response(("set_tempo", {"bpm": target})), response()])
    agent = ResponsesAgent("test-model", client=client)
    outcome = run_task(task, agent)
    assert outcome["passed"] and outcome["model_usage"]["total_tokens"] == 45
    serialized = json.dumps(client.requests)
    assert "evaluators" not in serialized and "project_property" not in serialized
    assert all(request["store"] is False for request in client.requests)
    assert all(request["parallel_tool_calls"] is False for request in client.requests)


def test_disallowed_tool_is_recoverable_and_audited():
    task = generate_task(0, 12)
    client = FakeClient([response(("delete_everything", {})), response()])
    outcome = run_task(task, ResponsesAgent("test", client=client))
    assert not outcome["passed"]
    assert "not allowed" in outcome["trajectory"][0]["error"]
    assert "not allowed" in json.dumps(client.requests[-1]["input"])


def test_turn_budget_is_enforced():
    task = generate_task(0, 12)
    client = FakeClient([response(("inspect_project", {}))])
    outcome = run_task(task, ResponsesAgent("test", client=client, max_turns=1))
    assert outcome["failure_class"] == "agent_error"
    assert "budget exhausted" in outcome["agent_error"]


def test_tool_schema_types_match_callable_signature():
    task = generate_task(0, 12)
    tools = tool_schemas(MusicEnvironment(task.initial_project, task.allowed_tools))
    tempo = next(t for t in tools if t["name"] == "set_tempo")
    assert tempo["parameters"]["properties"]["bpm"] == {"type": "number"}
    assert tempo["parameters"]["required"] == ["bpm"]


def test_provider_failure_is_not_an_agent_failure():
    class Broken:
        responses = None
        def create(self, **kwargs):
            raise ConnectionError("secret request body")
    client = Broken()
    client.responses = client
    outcome = run_task(generate_task(0, 12), ResponsesAgent("test", client=client))
    assert not outcome["infrastructure"]["ok"]
    assert "secret" not in json.dumps(outcome)
