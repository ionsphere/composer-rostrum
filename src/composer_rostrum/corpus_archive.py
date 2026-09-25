"""Package only referenced states and make every trajectory audio link portable."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil
import zipfile

from .corpus import CORPUS_VERSION
from .corpus_capture import sha256, write_json


def package_dataset(output: Path):
    output = output.resolve()
    dataset = output / "dataset"
    rows = [json.loads(line) for line in (dataset / "samples.jsonl").read_text(encoding="utf-8").splitlines()]
    selected = {dataset / name for name in ("samples.jsonl", "README.md", "validation.json")}
    selected.update(p for p in (dataset / "Effects").rglob("*") if p.is_file())
    loaded, audio = [], {}
    for row in rows:
        public = json.loads((dataset / row["input"]).read_text(encoding="utf-8"))
        private = json.loads((dataset / row["private_target"]).read_text(encoding="utf-8"))
        selected.update([dataset / row["input"], dataset / row["private_target"]])
        for folder in (public["input_state"], private["target_state"]):
            state = (dataset / folder).resolve()
            if not state.is_relative_to(dataset):
                raise ValueError("state path escapes dataset")
            selected.update(p for p in state.rglob("*") if p.is_file())
            if (state / "render.wav").exists():
                audio[sha256(state / "render.wav")] = state / "render.wav"
        loaded.append((row, public, private))

    cards = []
    for row, public, private in loaded:
        # Preserve the exact Lua/JSFX sources used for capture, including studio
        # variants when a recovered run spans a bridge fix.
        if "studio_files" not in private:
            render_event = next((e for e in private["trajectory"] if isinstance(e.get("result"), dict)
                                 and "path" in e["result"] and "content_hash" in e["result"]), None)
            if render_event:
                raw = render_event["result"]["path"].replace("\\", "/").removeprefix("//?/")
                worker = (output / raw).resolve().parent.parent
                if worker.is_relative_to(output) and (worker / "bridge").is_dir():
                    sources = sorted(p for p in (worker / "bridge").iterdir() if p.is_file())
                    signature = hashlib.sha256("".join(sha256(p) for p in sources).encode()).hexdigest()
                    private["studio_files"] = {}
                    for source in sources:
                        relative = f"studio/{signature}/{source.name}"
                        target = dataset / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, target)
                        private["studio_files"][relative] = sha256(target)
        for relative, digest in private.get("studio_files", {}).items():
            path = (dataset / relative).resolve()
            if not path.is_relative_to(dataset) or sha256(path) != digest:
                raise ValueError("captured studio source is missing or changed")
            selected.add(path)
        for event in private["trajectory"]:
            result = event.get("result")
            if not isinstance(result, dict) or "path" not in result or "content_hash" not in result:
                continue
            digest = result["content_hash"]
            if digest not in audio:
                raw = result["path"].replace("\\", "/").removeprefix("//?/")
                # Re-packaging resolves previously archived paths at dataset root.
                source = (dataset / raw).resolve()
                if not source.is_file():
                    source = (output / raw).resolve()
                if not source.is_relative_to(output) or sha256(source) != digest:
                    raise ValueError("trajectory audio is missing, outside capture, or has changed")
                target = dataset / "observations" / row["id"] / f"{digest}.wav"
                target.parent.mkdir(parents=True, exist_ok=True)
                if source != target:
                    shutil.copyfile(source, target)
                audio[digest] = target
            selected.add(audio[digest])
            result["path"] = audio[digest].relative_to(dataset).as_posix()
        private["artifact_path_base"] = "dataset-root"
        write_json(dataset / row["private_target"], private)
        source, target = public["input_state"], private["target_state"]
        escaped_prompt = html.escape(public["prompt"])
        links = " · ".join(f'<a href="{html.escape(path, quote=True)}">{label}</a>' for label, path in [
            ("Input REAPER project", source + "/project.rpp"), ("Target REAPER project", target + "/project.rpp"),
            ("Input IR", source + "/project.music-ir.json"), ("Target IR", target + "/project.music-ir.json"),
            ("Trace and evaluation", row["private_target"])])
        before_audio = f'<label>Before<audio controls preload="none" src="{source}/render.wav"></audio></label>' if (dataset / source / "render.wav").exists() else '<p>Empty input arrangement</p>'
        cards.append(f'<article data-split="{row["split"]}" data-stage="{row["stage"]}"><h2>{row["id"]}</h2>'
            f'<p class="meta">{row["split"]} · {row["stage"]}</p><p>{escaped_prompt}</p><p>{links}</p>'
            f'<div class="audio">{before_audio}<label>After<audio controls preload="none" src="{target}/render.wav"></audio></label></div></article>')
    stages = "".join(f'<option>{html.escape(stage)}</option>' for stage in sorted({row["stage"] for row in rows}))
    catalog = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>REAPER evaluation corpus</title><style>
body{font:16px/1.5 system-ui,sans-serif;max-width:1000px;margin:40px auto;padding:0 20px;background:#f5f7fa;color:#1d2937}
header{margin-bottom:28px}h1{font-size:30px}h2{font-size:19px}article{background:white;border:1px solid #d4dce6;border-radius:10px;padding:22px;margin:18px 0}
a{color:#175fb0}input,select{padding:10px;border:1px solid #9eabbc;border-radius:5px;font:inherit;margin:4px}input{min-width:260px}.meta{color:#536478}
.audio{display:flex;gap:24px;flex-wrap:wrap}audio{display:block;width:300px;max-width:100%}label{display:block}[hidden]{display:none!important}
    </style><header><h1>REAPER native evaluation corpus</h1>
<p>Procedural reference demonstrations. Browse prompts, compare native states, and listen to before/after audio. Targets and traces are for evaluators; do not expose this catalog to an evaluated agent.</p>
<label for="search">Search prompts</label><input id="search" placeholder="Search notes, fades, RMS…">
<select id="split" aria-label="Dataset split"><option value="">All splits</option><option>train</option><option>dev</option><option>test</option></select>
    <select id="stage" aria-label="Workflow stage"><option value="">All stages</option>""" + stages + """</select>
    <p id="count" aria-live="polite"></p></header><main>""" + "\n".join(cards) + """</main><script>
const search=document.getElementById('search'),split=document.getElementById('split'),stage=document.getElementById('stage');
function filter(){let count=0;document.querySelectorAll('article').forEach(card=>{card.hidden=!(card.textContent.toLowerCase().includes(search.value.toLowerCase())&&(!split.value||card.dataset.split===split.value)&&(!stage.value||card.dataset.stage===stage.value));if(!card.hidden)count++});document.getElementById('count').textContent=count+' samples shown'}
[search,split,stage].forEach(control=>control.addEventListener('input',filter));filter();
</script></html>"""
    (dataset / "catalog.html").write_text(catalog, encoding="utf-8", newline="\n")
    selected.add(dataset / "catalog.html")
    files = {p.relative_to(dataset).as_posix(): sha256(p) for p in sorted(selected)}
    write_json(dataset / "checksums.json", files)
    corpus_version = json.loads((dataset / "validation.json").read_text(encoding="utf-8")).get("corpus", CORPUS_VERSION)
    archive = output / f"{corpus_version}.zip"
    temporary = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for relative in sorted([*files, "checksums.json"]):
            bundle.write(dataset / relative, relative)
    temporary.replace(archive)
    write_json(output / "archive.json", {"file": archive.name, "sha256": sha256(archive), "bytes": archive.stat().st_size})
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    print(package_dataset(parser.parse_args().capture))


if __name__ == "__main__":
    main()
