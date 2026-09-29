"""Local Transformers agent using the same action protocol as the SFT export."""
from __future__ import annotations

import json

from .environment import ToolError
from .model_agent import tool_schemas
from .training_protocol import SYSTEM, action, observation, parse_action, prompt


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

    def solve(self, task, environment):
        self.decisions = []
        schemas = tool_schemas(environment)
        allowed = set(environment.allowed_tools)
        history = []
        for _ in range(self.max_turns):
            text = self.tokenizer.apply_chat_template([
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt(task.prompt, schemas, history)}],
                tokenize=False, add_generation_prompt=True)
            ids = self.tokenizer(text, add_special_tokens=False, return_tensors="pt").input_ids.to("cuda")
            with self.torch.inference_mode():
                output = self.model.generate(ids, attention_mask=self.torch.ones_like(ids),
                    max_new_tokens=self.max_new_tokens, do_sample=False,
                    pad_token_id=self.tokenizer.eos_token_id)
            raw = self.tokenizer.decode(output[0, ids.shape[1]:], skip_special_tokens=True).strip()
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
