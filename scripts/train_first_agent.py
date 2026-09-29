"""Train and measure the first local REAPER next-action adapter on one GPU."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import time


def load_rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--resume-adapter", type=Path,
                        help="Continue a previous LoRA adapter instead of starting a new one")
    parser.add_argument("--revision", default="7ae557604adf67be50417f59c2c2f167def9a775")
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--max-steps", type=int, default=180)
    parser.add_argument("--eval-samples", type=int, default=50)
    parser.add_argument("--generation-tokens", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--seed", type=int, default=20260927)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)

    import torch
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from composer_rostrum.training_protocol import parse_action

    if not torch.cuda.is_available():
        raise RuntimeError("this first run requires a CUDA GPU")
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    train_path, dev_path = args.data / "train.jsonl", args.data / "dev.jsonl"
    train_rows, dev_rows = load_rows(train_path), load_rows(dev_path)
    tokenizer = AutoTokenizer.from_pretrained(args.model, revision=args.revision)
    tokenizer.pad_token = tokenizer.eos_token

    def prefix(row):
        return tokenizer.apply_chat_template([
            {"role": "system", "content": row["system"]},
            {"role": "user", "content": row["prompt"]}],
            tokenize=False, add_generation_prompt=True)

    usable, skipped = [], 0
    for row in train_rows:
        prompt_ids = tokenizer(prefix(row), add_special_tokens=False).input_ids
        completion_ids = tokenizer(row["completion"] + tokenizer.eos_token,
                                   add_special_tokens=False).input_ids
        if len(prompt_ids) + len(completion_ids) > args.max_length:
            skipped += 1
            continue
        usable.append((row, prompt_ids, completion_ids))
    if not usable:
        raise ValueError("no training examples fit max-length")

    model = AutoModelForCausalLM.from_pretrained(args.model, revision=args.revision,
                                                 dtype=torch.bfloat16).to("cuda")
    model.config.use_cache = False
    if args.resume_adapter:
        model = PeftModel.from_pretrained(model, args.resume_adapter, is_trainable=True)
    else:
        model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05,
            bias="none", task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),
                                  lr=args.learning_rate, weight_decay=0.01)

    # Fixed, chain-held-out examples for an honest before/after comparison.
    rng = random.Random(args.seed)
    routing_dev = [row for row in dev_rows if row["corpus"] == "music-program-routing-v1"]
    other_dev = [row for row in dev_rows if row["corpus"] != "music-program-routing-v1"]
    selected = rng.sample(other_dev, min(args.eval_samples, len(other_dev))) + routing_dev
    def evaluate():
        model.eval()
        exact = tool = parsed = 0
        by_corpus = {}
        cases = []
        with torch.inference_mode():
            for row in selected:
                ids = tokenizer(prefix(row), return_tensors="pt", add_special_tokens=False).input_ids
                if ids.shape[1] > args.max_length - 100:
                    continue
                ids = ids.to("cuda")
                generated = model.generate(ids, attention_mask=torch.ones_like(ids),
                                           max_new_tokens=args.generation_tokens, do_sample=False,
                                           pad_token_id=tokenizer.eos_token_id)
                response = tokenizer.decode(generated[0, ids.shape[1]:], skip_special_tokens=True).strip()
                expected = json.loads(row["completion"])
                allowed = {entry["name"] for entry in json.loads(row["prompt"].split("Available tools: ", 1)[1].split("\n", 1)[0])}
                try:
                    actual = parse_action(response, allowed)
                    valid = True
                except (json.JSONDecodeError, ValueError):
                    actual, valid = None, False
                correct_tool = valid and actual["tool"] == expected["tool"]
                correct = actual == expected
                parsed += valid
                tool += correct_tool
                exact += correct
                family = row["corpus"]
                bucket = by_corpus.setdefault(family, {"n": 0, "tool": 0, "exact": 0})
                bucket["n"] += 1
                bucket["tool"] += correct_tool
                bucket["exact"] += correct
                cases.append({"id": row["id"], "expected": expected, "actual": actual,
                              "raw": response[:400]})
        return {"n": len(cases), "parsed": parsed, "tool_correct": tool,
                "action_exact": exact, "by_corpus": by_corpus, "cases": cases}

    started = time.time()
    baseline = evaluate()
    print(f"baseline: {baseline['action_exact']}/{baseline['n']} exact, "
          f"{baseline['tool_correct']}/{baseline['n']} tool", flush=True)
    order = list(range(len(usable)))
    rng.shuffle(order)
    losses = []
    model.train()
    for step in range(args.max_steps):
        if step and step % len(order) == 0:
            rng.shuffle(order)
        _, prompt_ids, completion_ids = usable[order[step % len(order)]]
        ids = torch.tensor([prompt_ids + completion_ids], device="cuda")
        labels = torch.tensor([[-100] * len(prompt_ids) + completion_ids], device="cuda")
        optimizer.zero_grad(set_to_none=True)
        loss = model(input_ids=ids, labels=labels).loss
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        losses.append(float(loss.detach().cpu()))
        if (step + 1) % 25 == 0:
            print(f"step {step+1}/{args.max_steps}: mean loss {sum(losses[-25:])/25:.4f}", flush=True)
    model.config.use_cache = True
    model.gradient_checkpointing_disable()
    adapted = evaluate()
    model.save_pretrained(args.output / "adapter", safe_serialization=True)
    tokenizer.save_pretrained(args.output / "adapter")
    report = {"base_model": args.model, "base_revision": args.revision,
              "resume_adapter": str(args.resume_adapter) if args.resume_adapter else None,
              "adapter": "LoRA r8 alpha16", "seed": args.seed,
              "max_length": args.max_length, "max_steps": args.max_steps,
              "generation_tokens": args.generation_tokens,
              "learning_rate": args.learning_rate, "train_examples": len(usable),
              "skipped_overlength": skipped, "dev_examples": len(dev_rows),
              "train_sha256": hashlib.sha256(train_path.read_bytes()).hexdigest(),
              "dev_sha256": hashlib.sha256(dev_path.read_bytes()).hexdigest(),
              "loss_first_25": sum(losses[:25]) / min(25, len(losses)),
              "loss_last_25": sum(losses[-25:]) / min(25, len(losses)),
              "elapsed_seconds": round(time.time() - started, 1),
              "baseline": {k: v for k, v in baseline.items() if k != "cases"},
              "adapted": {k: v for k, v in adapted.items() if k != "cases"}}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "dev-predictions.json").write_text(json.dumps(
        {"baseline": baseline["cases"], "adapted": adapted["cases"]}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
