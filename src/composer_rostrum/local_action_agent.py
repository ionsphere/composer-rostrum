"""Local Transformers agent using the same action protocol as the SFT export."""
from __future__ import annotations

import json

from .environment import ToolError
from .model_agent import tool_schemas
from .music_programs import ProgramChoice, ROUTING_SYSTEM, ROUTING_TOOLS, choose_music_program
from .training_protocol import SYSTEM, action, compact, observation, parse_action, prompt


class LocalActionAgent:
    def __init__(self, base_model: str, adapter: str | None = None,
                 max_turns: int = 20, max_new_tokens: int = 256,
                 revision: str = "7ae557604adf67be50417f59c2c2f167def9a775"):
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(adapter or base_model,
                                                        revision=None if adapter else revision)
        model = AutoModelForCausalLM.from_pretrained(base_model, revision=revision,
                                                     dtype=torch.bfloat16).to("cuda")
        self.model = PeftModel.from_pretrained(model, adapter).eval() if adapter else model.eval()
        self.max_turns, self.max_new_tokens = max_turns, max_new_tokens
        self.decisions = []
        self.route_decision = None

    def _generate(self, system: str, user_prompt: str) -> str:
        text = self.tokenizer.apply_chat_template([
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt}],
            tokenize=False, add_generation_prompt=True)
        ids = self.tokenizer(text, add_special_tokens=False, return_tensors="pt").input_ids.to("cuda")
        with self.torch.inference_mode():
            output = self.model.generate(ids, attention_mask=self.torch.ones_like(ids),
                max_new_tokens=self.max_new_tokens, do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id)
        return self.tokenizer.decode(output[0, ids.shape[1]:], skip_special_tokens=True).strip()

    def choose_program(self, task_prompt: str, required_operations: list[str], programs,
                       preferred: str | None = None) -> ProgramChoice:
        safe = choose_music_program(required_operations, programs, preferred)
        if safe.status == "unavailable":
            self.route_decision = {"tool": "report_unavailable", "reason": safe.reason,
                                   "source": "capability check"}
            return safe
        catalog = [{"name": program.name, "installed": program.installed,
                    "usable": program.usable, "operations": program.operations,
                    "dialect": program.dialect, "reason": program.reason} for program in programs]
        routing_prompt = (f"Task: {task_prompt}\nRequired operations: {compact(required_operations)}\n"
                          f"Discovered programs: {compact(catalog)}\n"
                          f"Available tools: {compact(ROUTING_TOOLS)}\nNext action (JSON only):")
        if preferred:
            routing_prompt = routing_prompt.replace("\nAvailable tools:",
                f"\nRequired program: {preferred}\nAvailable tools:")
        raw = self._generate(ROUTING_SYSTEM, routing_prompt)
        try:
            decision = parse_action(raw, {"select_music_program", "report_unavailable"})
        except (json.JSONDecodeError, ValueError) as exc:
            self.route_decision = {"raw": raw, "error": str(exc)}
            return ProgramChoice("unavailable", None, "Model could not choose a usable music program.",
                                 safe.required_operations)
        self.route_decision = decision
        if decision["tool"] != "select_music_program":
            return ProgramChoice("unavailable", None, "Model did not select a music program.",
                                 safe.required_operations)
        selected = decision["arguments"].get("program")
        validated = choose_music_program(required_operations, programs, selected)
        if selected not in {program.name for program in programs} or validated.status != "selected" or (preferred and selected != preferred):
            return ProgramChoice("unavailable", None, "Model selected an unavailable or incapable music program.",
                                 safe.required_operations)
        return validated

    def solve(self, task, environment):
        self.decisions = []
        schemas = tool_schemas(environment)
        allowed = set(environment.allowed_tools)
        history = []
        for _ in range(self.max_turns):
            raw = self._generate(SYSTEM, prompt(task.prompt, schemas, history))
            try:
                decision = parse_action(raw, allowed)
            except (json.JSONDecodeError, ValueError) as exc:
                self.decisions.append({"raw": raw, "error": str(exc)})
                history.append({"action": {"invalid": raw[:200]},
                                "observation": {"error": str(exc)}})
                continue
            self.decisions.append(decision)
            if decision["tool"] == "finish":
                return
            try:
                result = environment.call(decision["tool"], **decision["arguments"])
                observed = observation(decision["tool"], result)
            except (ToolError, TypeError, ValueError, KeyError) as exc:
                observed = {"error": f"{type(exc).__name__}: {exc}"}
            history.append({"action": action(decision["tool"], decision["arguments"]),
                            "observation": observed})
        raise RuntimeError("local agent turn budget exhausted")
