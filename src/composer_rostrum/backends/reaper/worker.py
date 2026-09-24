"""Own exactly one REAPER process and an isolated resource directory per run."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from ..base import BackendError


class ReaperWorker:
    def __init__(self, executable: str | Path, workspace: Path):
        self.executable = Path(executable).resolve()
        self.workspace = workspace.resolve()
        self.process = None
        self.log = None
        self.lock_path = self.workspace / "worker.lock"
        self.owns_lock = False

    def start(self) -> None:
        try:
            with self.lock_path.open("x", encoding="utf-8") as lock:
                lock.write(str(os.getpid()))
            self.owns_lock = True
        except FileExistsError as exc:
            raise BackendError("workspace already has an owner; use a fresh workspace after an unclean exit") from exc
        try:
            self._start()
        except BaseException:
            self.close()
            raise

    def _start(self) -> None:
        if not self.executable.is_file():
            raise BackendError(f"REAPER executable not found: {self.executable}")
        profile = self.workspace / "profile"
        profile.mkdir(exist_ok=True)
        bridge_dir = Path(__file__).parent / "bridge"
        staged_bridge = self.workspace / "bridge"
        shutil.copytree(bridge_dir, staged_bridge, dirs_exist_ok=True)
        effects = profile / "Effects" / "Rostrum"
        effects.mkdir(parents=True, exist_ok=True)
        for effect in bridge_dir.glob("*.jsfx"):
            shutil.copyfile(effect, effects / effect.name)
        config = profile / "reaper.ini"
        if not config.exists():
            plugins = profile / "empty-plugins"
            plugins.mkdir(exist_ok=True)
            config.write_text(f"[REAPER]\nnewprojdo=0\nvstpath64={plugins}\nvstpath={plugins}\n"
                              "[audioconfig]\nmode=0\nwaveout_srate=48000\nwaveout_bps=16\n"
                              "waveout_devicein=-1\nwaveout_deviceout=0\nwaveout_nch_in=0\n"
                              "waveout_nch_out=2\nwaveout_bs=1024\nwaveout_numblocks=8\n", encoding="utf-8")
        bootstrap = self.workspace / "start.lua"
        bootstrap.write_text("ROSTRUM_WORKSPACE = " + json.dumps(self.workspace.as_posix(), ensure_ascii=False) +
            "\nlocal ok,err=xpcall(function() dofile(" + json.dumps((staged_bridge / "rostrum_bridge.lua").as_posix(), ensure_ascii=False) +
            ") end,debug.traceback)\nif not ok then local f=io.open(ROSTRUM_WORKSPACE..'/logs/bridge-error.txt','w'); "
            "if f then f:write(err); f:close() end end\n", encoding="utf-8")
        self.log = (self.workspace / "logs" / "worker.log").open("ab")
        options = {}
        if os.name == "nt":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 1 if os.environ.get("ROSTRUM_REAPER_VISIBLE") == "1" else 0
            options["startupinfo"] = startup
        try:
            self.process = subprocess.Popen([str(self.executable), "-newinst", "-nosplash", "-cfgfile",
                                             str(config), str(bootstrap)], stdout=self.log, stderr=self.log, **options)
        except Exception:
            self.log.close()
            raise

    def check(self) -> None:
        if self.process is not None and self.process.poll() is not None:
            raise BackendError(f"REAPER worker exited with code {self.process.returncode}")
        error_path = self.workspace / "logs" / "bridge-error.txt"
        if error_path.exists():
            raise BackendError("REAPER bridge startup failed: " + error_path.read_text(encoding="utf-8")[:2000])

    def close(self) -> None:
        try:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        finally:
            if self.log is not None:
                self.log.close()
            if self.owns_lock:
                self.lock_path.unlink(missing_ok=True)
                self.owns_lock = False
