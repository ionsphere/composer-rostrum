"""Add split-safe music-program selection and abstention examples to SFT data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from composer_rostrum.music_programs import MusicProgram, ROUTING_SYSTEM, ROUTING_TOOLS, choose_music_program
from composer_rostrum.training_protocol import compact


INTENTS = {
    "mute_track": ["Mute the drum track", "Silence the drum channel", "Turn off the drums track",
                   "Mute drums without touching the other tracks", "Make the drum track silent",
                   "Switch off playback for the drum channel"],
    "set_tempo": ["Set the session to 128 BPM", "Change the project tempo to 128",
                  "Make the song run at 128 beats per minute", "Adjust the tempo to 128 BPM",
                  "Set the beat rate to 128", "Change BPM to 128"],
    "add_notes": ["Write a short MIDI melody", "Add notes to the bass clip",
                  "Program a four-note riff", "Place MIDI notes on the piano track",
                  "Compose a few notes in the clip", "Enter a bass line as MIDI"],
    "render": ["Render the project to audio", "Export a WAV mix",
               "Bounce the song", "Make an audio render of the session",
               "Print the mix to a WAV file", "Export the final audio"],
    "comp_audio": ["Comp the best vocal takes", "Assemble a composite from three takes",
                   "Choose the best phrase from each vocal pass", "Make a vocal comp",
                   "Combine good sections of the takes", "Stitch the best performances together"],
}
STATES = ((True, False), (True, True), (False, True), (False, False))


def programs_for_state(reaper_ready: bool, audacity_ready: bool) -> list[MusicProgram]:
    return [
        MusicProgram("reaper", "reaper" if reaper_ready else None, reaper_ready,
                     reaper_ready, ("mute_track", "set_tempo", "add_notes", "render"),
                     "Rostrum REAPER bridge"),
        MusicProgram("audacity", "audacity", True, audacity_ready,
                     ("mute_track",), "Audacity scripting commands",
                     None if audacity_ready else "scripting connection not verified"),
    ]


def routing_rows(split: str):
    phrase_indices = range(4) if split == "train" else range(4, 6)
    for operation, phrases in INTENTS.items():
        for index in phrase_indices:
            for state_index, (reaper_ready, audacity_ready) in enumerate(STATES):
                programs = programs_for_state(reaper_ready, audacity_ready)
                choice = choose_music_program([operation], programs)
                completion = ({"tool": "select_music_program", "arguments": {"program": choice.program}}
                              if choice.status == "selected" else
                              {"tool": "report_unavailable", "arguments": {"reason": choice.reason}})
                catalog = [{"name": program.name, "installed": program.installed,
                            "usable": program.usable, "operations": program.operations,
                            "dialect": program.dialect,
                            "reason": program.reason} for program in programs]
                yield {"id": f"route-{operation}-{index}-{state_index}",
                       "sample_id": f"route-{operation}-{index}", "corpus": "music-program-routing-v1",
                       "chain_id": f"route-{operation}-{index}", "split": split,
                       "system": ROUTING_SYSTEM,
                       "prompt": (f"Task: {phrases[index]}\nRequired operations: {compact([operation])}\n"
                                  f"Discovered programs: {compact(catalog)}\n"
                                  f"Available tools: {compact(ROUTING_TOOLS)}\nNext action (JSON only):"),
                       "completion": compact(completion)}


def export(existing: Path, output: Path) -> dict:
    source_manifest = json.loads((existing / "manifest.json").read_text(encoding="utf-8"))
    if source_manifest.get("test_split_exported") is not False:
        raise ValueError("source training export must exclude test")
    for split in ("train", "dev"):
        digest = hashlib.sha256((existing / f"{split}.jsonl").read_bytes()).hexdigest()
        if source_manifest["files"][split] != digest:
            raise ValueError(f"source {split} checksum mismatch")
    output.mkdir(parents=True, exist_ok=False)
    counts = {}
    hashes = {}
    for split in ("train", "dev"):
        original = (existing / f"{split}.jsonl").read_text(encoding="utf-8")
        rows = list(routing_rows(split))
        # Oversample routing in training so a short continuation sees both
        # program choice and REAPER editing; keep dev examples unique.
        repetitions = 16 if split == "train" else 1
        with (output / f"{split}.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(original)
            for repeat in range(repetitions):
                for row in rows:
                    entry = {**row, "id": row["id"] + f":{repeat}"}
                    handle.write(compact(entry) + "\n")
        counts[split] = {"original": len(original.splitlines()), "routing_unique": len(rows),
                         "routing_written": len(rows) * repetitions}
        hashes[split] = hashlib.sha256((output / f"{split}.jsonl").read_bytes()).hexdigest()
    result = {"format": "rostrum-next-action-plus-routing-v1", "counts": counts,
              "source_format": source_manifest["format"], "source_files": source_manifest["files"],
              "files": hashes, "test_split_exported": False}
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("existing", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.existing, args.output), indent=2))


if __name__ == "__main__":
    main()
