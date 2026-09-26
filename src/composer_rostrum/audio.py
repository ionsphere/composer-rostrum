"""Deterministic PCM WAV observations (no optional DSP dependencies)."""
from __future__ import annotations

import hashlib
import math
import wave
from pathlib import Path


def analyze_wav(path: str | Path) -> dict:
    path = Path(path)
    with wave.open(str(path), "rb") as wav:
        channels, width, rate, frames = wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()
        if width not in (1, 2, 3, 4) or not frames or rate <= 0:
            raise ValueError("expected a non-empty integer PCM WAV")
        peak = square_sum = 0.0
        pcm_hash = hashlib.sha256()
        count = clipped = silent = 0
        while True:
            data = wav.readframes(8192)
            if not data:
                break
            if len(data) % (width * channels):
                raise ValueError("truncated PCM frame")
            pcm_hash.update(data)
            for offset in range(0, len(data), width):
                sample = (data[offset] - 128) / 128 if width == 1 else int.from_bytes(
                    data[offset:offset + width], "little", signed=True) / (2 ** (width * 8 - 1))
                peak = max(peak, abs(sample))
                square_sum += sample * sample
                count += 1
                clipped += abs(sample) >= 1 - 1 / (2 ** (width * 8 - 1))
                silent += abs(sample) < 1e-5
        if count != frames * channels:
            raise ValueError("truncated WAV payload")
    rms = math.sqrt(square_sum / count)
    result = {"duration_seconds": frames / rate, "sample_rate": rate, "channels": channels,
            "frames": frames, "sample_width": width, "peak": peak, "rms": rms,
            "rms_dbfs": 20 * math.log10(rms) if rms else None,
            "silent": peak < 1e-5, "silence_fraction": silent / count,
            "clipped_samples": clipped, "content_hash": hashlib.sha256(path.read_bytes()).hexdigest()}
    result["pcm_hash"] = pcm_hash.hexdigest()
    return result


def write_fixture(path: Path, duration: float = 3.2, rate: int = 48000,
                  kind: str = "tone") -> None:
    """Benchmark-owned deterministic tone, kick, or plucked-string proxy."""
    import struct
    if kind not in ("tone", "kick", "guitar"):
        raise ValueError("unknown procedural audio fixture")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        def sample(i):
            t = i / rate
            if kind == "tone":
                return struct.pack("<h", round(12000 * math.sin(2 * math.pi * 220 * i / rate)
                                                   * math.exp(-i / rate) * min(1, i / 240)))
            if kind == "kick":
                phase = 2 * math.pi * (48*t + 85*0.018*(1-math.exp(-t/0.018)))
                value = 0.64 * math.sin(phase) * math.exp(-t/0.075) * min(1, i/24)
            elif kind == "guitar":
                partials = sum(math.sin(2*math.pi*110*h*t) / h for h in range(1, 7))
                value = 0.22 * partials * math.exp(-t/0.16) * min(1, i/80)
            return struct.pack("<h", round(32767 * max(-1, min(1, value))))
        wav.writeframes(b"".join(sample(i) for i in range(round(rate * duration))))
