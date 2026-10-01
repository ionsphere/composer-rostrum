"""Discover music programs and route canonical intents only to usable adapters."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import shutil
import sys


ROUTING_SYSTEM = ("You are a music-production agent choosing a program. Select only an installed, "
          "usable program that supports every required operation. If none does, call "
          "report_unavailable and say why. Reply with exactly one JSON action. Never "
          "claim that an installed but disconnected program is usable.")
ROUTING_TOOLS = [
    {"name": "select_music_program", "parameters": {"program": "string"}},
    {"name": "report_unavailable", "parameters": {"reason": "string"}},
]


@dataclass(frozen=True)
class MusicProgram:
    name: str
    executable: str | None
    installed: bool
    usable: bool
    operations: tuple[str, ...]
    dialect: str
    reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProgramChoice:
    status: str
    program: str | None
    reason: str
    required_operations: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _executable(env_name: str, command: str, windows_paths: tuple[str, ...]) -> str | None:
    configured = os.environ.get(env_name)
    if configured:
        path = Path(configured).expanduser()
        return str(path.resolve()) if path.is_file() else None
    found = shutil.which(command)
    if found:
        return str(Path(found).resolve())
    if sys.platform == "win32":
        for candidate in windows_paths:
            path = Path(candidate)
            if path.is_file():
                return str(path.resolve())
    return None


def _audacity_connected() -> bool:
    try:
        from .backends.audacity import available
        return available()
    except (OSError, ImportError):
        return False


def discover_music_programs() -> list[MusicProgram]:
    """Executable presence is separate from a verified automation connection."""
    reaper = _executable("REAPER_EXECUTABLE", "reaper",
        (r"C:\Program Files\REAPER (x64)\reaper.exe", r"C:\Program Files\REAPER\reaper.exe"))
    audacity = _executable("AUDACITY_EXECUTABLE", "audacity",
        (r"C:\Program Files\Audacity\Audacity.exe",))
    audacity_connected = bool(audacity) and _audacity_connected()
    return [
        MusicProgram("reaper", reaper, bool(reaper), bool(reaper),
                     ("mute_track", "set_track_gain", "set_tempo", "set_clip_gain",
                      "split_audio_clip", "add_notes", "render"), "Rostrum REAPER bridge",
                     None if reaper else "REAPER executable not found"),
        MusicProgram("audacity", audacity, bool(audacity), audacity_connected,
                     ("import_audio", "mute_track", "solo_track", "set_track_gain",
                      "set_track_pan", "rename_track", "split_audio_clip", "fade_audio",
                      "normalize_audio", "render"), "Audacity mod-script-pipe",
                     None if audacity_connected else "Audacity scripting connection unavailable" if audacity else
                     "Audacity executable not found"),
    ]


def choose_music_program(required_operations: list[str] | tuple[str, ...],
                         programs: list[MusicProgram], preferred: str | None = None) -> ProgramChoice:
    required = tuple(sorted(set(required_operations)))
    if not required:
        return ProgramChoice("unavailable", None,
                             "No required music operation was specified.", required)
    candidates = [program for program in programs if program.usable and
                  set(required).issubset(program.operations)]
    if preferred:
        candidates = [program for program in candidates if program.name == preferred]
    if candidates:
        # Prefer the narrow audio editor for its supported action, otherwise the DAW.
        candidates.sort(key=lambda program: (program.name != "audacity" if required == ("mute_track",)
                                             else program.name != "reaper", program.name))
        return ProgramChoice("selected", candidates[0].name, "usable adapter covers every required operation", required)
    requirement = ", ".join(required) if required else "the requested task"
    suffix = f" for {preferred}" if preferred else ""
    return ProgramChoice("unavailable", None,
                         f"No connected music program supports {requirement}{suffix}.", required)


def translate_mute_track(program: str, track_id: str, muted: bool,
                         *, audacity_track_index: int | None = None) -> list[dict | str]:
    """Two concrete dialects for the same canonical mute intent.

    Audacity selects by zero-based track index; callers must resolve that index
    from a verified live project before sending either command.
    """
    if program == "reaper":
        return [{"tool": "mute_track", "arguments": {"track_id": track_id, "muted": muted}}]
    if program == "audacity":
        if audacity_track_index is None or audacity_track_index < 0:
            raise ValueError("Audacity requires a verified nonnegative track index")
        return [f"SelectTracks: Track={audacity_track_index} TrackCount=1 Mode=Set",
                f"SetTrackAudio: Mute={int(muted)}"]
    raise ValueError(f"unsupported music program: {program}")
