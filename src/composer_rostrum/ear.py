"""Deterministic PCM ear: measurable differences and explicit audio oracles.

This is a signal comparator, not a model of human preference. Inputs are bounded
uncompressed PCM WAVs. Every reported decision names its numeric threshold.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import wave


def _db(value: float) -> float | None:
    return round(20 * math.log10(value), 6) if value > 0 else None


def _decode(raw: bytes, width: int):
    if width == 1:
        return [(byte - 128) / 128 for byte in raw]
    if width == 2:
        return [value / 32768 for (value,) in struct.iter_unpack("<h", raw)]
    if width == 3:
        return [int.from_bytes(raw[i:i+3], "little", signed=True) / 8388608
                for i in range(0, len(raw), 3)]
    if width == 4:
        return [value / 2147483648 for (value,) in struct.iter_unpack("<i", raw)]
    raise ValueError("only 8/16/24/32-bit integer PCM WAV is supported")


def read_pcm(path: str | Path, max_seconds: float = 30) -> dict:
    path = Path(path)
    with wave.open(str(path), "rb") as wav:
        if wav.getcomptype() != "NONE" or wav.getnchannels() not in (1, 2):
            raise ValueError("expected uncompressed mono/stereo PCM WAV")
        rate, channels, frames = wav.getframerate(), wav.getnchannels(), wav.getnframes()
        if frames / rate > max_seconds:
            raise ValueError(f"WAV exceeds {max_seconds:g}-second analysis limit")
        width = wav.getsampwidth()
        raw = wav.readframes(frames)
    values = _decode(raw, width)
    if len(values) != frames * channels:
        raise ValueError("truncated PCM data")
    left = values[::channels]
    right = values[1::channels] if channels == 2 else None
    mono = [(a + b) * 0.5 for a, b in zip(left, right)] if right else left
    return {"path": str(path), "sample_rate": rate, "channels": channels,
            "sample_width": width, "frames": frames, "pcm_sha256": hashlib.sha256(raw).hexdigest(),
            "samples": values, "mono": mono, "left": left, "right": right}


def _rms(values) -> float:
    return math.sqrt(sum(value * value for value in values) / len(values)) if values else 0.0


def _envelope(mono: list[float], rate: int, window_ms: int = 10) -> list[float]:
    width = max(1, round(rate * window_ms / 1000))
    return [_rms(mono[i:i+width]) for i in range(0, len(mono), width)]


def _pitch(mono: list[float], rate: int, onset_frame: int, offset_frame: int):
    """Autocorrelation F0 for reasonably monophonic material; confidence gates use."""
    middle = (onset_frame + offset_frame) // 2
    stride = max(1, rate // 12000)
    size = 2048
    first = max(0, middle - size * stride // 2)
    data = mono[first:first + size * stride:stride]
    if len(data) < size or _rms(data) < 0.001:
        return None, 0.0
    mean = sum(data) / len(data)
    data = [value - mean for value in data]
    decimated_rate = rate / stride
    min_lag = max(2, round(decimated_rate / 1000))
    max_lag = min(size // 2, round(decimated_rate / 50))
    scores = []
    for lag in range(min_lag, max_lag + 1):
        left = data[:-lag]
        right = data[lag:]
        numerator = sum(a*b for a, b in zip(left, right))
        denominator = math.sqrt(sum(a*a for a in left) * sum(b*b for b in right))
        score = numerator / denominator if denominator else 0.0
        scores.append((lag, score))
    best_lag, best_score = max(scores, key=lambda pair: pair[1])
    # A periodic signal also correlates at 2x/3x its period. Prefer the first
    # strong local peak to avoid labeling a 440 Hz tone as 220 or 110 Hz.
    for index in range(1, len(scores) - 1):
        lag, score = scores[index]
        if score >= 0.9 and score >= scores[index-1][1] and score >= scores[index+1][1]:
            best_lag, best_score = lag, score
            break
    return (round(decimated_rate / best_lag, 3) if best_lag and best_score >= 0.75 else None,
            round(max(0.0, best_score), 4))


def _spectrum(mono: list[float], rate: int, onset_frame: int, offset_frame: int):
    """One Hann-windowed radix-2 FFT; normalized log bands describe timbre."""
    size = 4096
    middle = (onset_frame + offset_frame) // 2
    start = max(0, min(len(mono) - size, middle - size // 2))
    source = mono[start:start + size]
    if len(source) < size or _rms(source) < 0.001:
        return None, None
    values = [complex(sample * (0.5 - 0.5 * math.cos(2 * math.pi * i / (size - 1))), 0)
              for i, sample in enumerate(source)]
    # In-place bit-reversal permutation.
    j = 0
    for i in range(1, size):
        bit = size >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            values[i], values[j] = values[j], values[i]
    width = 2
    while width <= size:
        angle = -2 * math.pi / width
        root = complex(math.cos(angle), math.sin(angle))
        for start in range(0, size, width):
            factor = 1 + 0j
            half = width // 2
            for offset in range(half):
                even = values[start + offset]
                odd = factor * values[start + offset + half]
                values[start + offset] = even + odd
                values[start + offset + half] = even - odd
                factor *= root
        width *= 2
    upper = min(16000, rate / 2)
    boundaries = [50 * (upper / 50) ** (i / 16) for i in range(17)]
    bands = [0.0] * 16
    weighted = total = 0.0
    for bin_index in range(1, size // 2):
        frequency = bin_index * rate / size
        power = abs(values[bin_index]) ** 2
        weighted += frequency * power
        total += power
        if frequency < boundaries[0] or frequency >= boundaries[-1]:
            continue
        index = min(15, int(16 * math.log(frequency / 50) / math.log(upper / 50)))
        bands[index] += power
    band_total = sum(bands)
    profile = [round(10 * math.log10(max(power / band_total, 1e-10)), 4) for power in bands] if band_total else None
    return (round(weighted / total, 3) if total else None), profile


def describe(pcm: dict) -> dict:
    mono, rate = pcm["mono"], pcm["sample_rate"]
    envelope = _envelope(pcm["samples"], rate * pcm["channels"])
    floor = max(10 ** (-55 / 20), max(envelope, default=0) * 0.01)
    active = [index for index, energy in enumerate(envelope) if energy > floor]
    onset_frame = active[0] * round(rate / 100) if active else 0
    offset_frame = min(len(mono), (active[-1] + 1) * round(rate / 100)) if active else 0
    pitch, confidence = _pitch(mono, rate, onset_frame, offset_frame) if active else (None, 0.0)
    centroid, bands = _spectrum(mono, rate, onset_frame, offset_frame) if active else (None, None)
    left_rms = _rms(pcm["left"])
    right_rms = _rms(pcm["right"]) if pcm["right"] is not None else None
    balance = _db(right_rms / left_rms) if right_rms is not None and left_rms else None
    return {"duration_ms": round(1000 * pcm["frames"] / rate, 3),
            "onset_ms": active[0] * 10 if active else None,
            "offset_ms": (active[-1] + 1) * 10 if active else None,
            "rms_dbfs": _db(_rms(pcm["samples"])),
            "peak_dbfs": _db(max((abs(v) for v in pcm["samples"]), default=0)),
            "left_rms_dbfs": _db(left_rms), "right_rms_dbfs": _db(right_rms) if right_rms is not None else None,
            "stereo_balance_db": balance, "pitch_hz": pitch, "pitch_confidence": confidence,
            "spectral_centroid_hz": centroid, "spectral_bands_db": bands,
            "active_windows": len(active), "pcm_sha256": pcm["pcm_sha256"]}


def _waveform_snr(reference: list[float], candidate: list[float], shift_frames: int = 0,
                  gain: float = 1.0) -> float | None:
    length = max(len(reference) + max(shift_frames, 0), len(candidate))
    signal = error = 0.0
    for i in range(length):
        source_index = i - shift_frames
        expected = reference[source_index] * gain if 0 <= source_index < len(reference) else 0.0
        actual = candidate[i] if i < len(candidate) else 0.0
        signal += expected * expected
        error += (expected - actual) ** 2
    if signal == 0:
        return None
    return round(10 * math.log10(signal / error), 4) if error else 200.0


def compare(reference: str | Path, candidate: str | Path) -> dict:
    a, b = read_pcm(reference), read_pcm(candidate)
    if a["sample_rate"] != b["sample_rate"] or a["channels"] != b["channels"]:
        raise ValueError("sample rate and channel count must match; no implicit resampling")
    first, second = describe(a), describe(b)
    differences = {}
    for key in ("duration_ms", "onset_ms", "offset_ms", "rms_dbfs", "peak_dbfs", "stereo_balance_db"):
        x, y = first[key], second[key]
        differences[key] = round(y-x, 6) if x is not None and y is not None else None
    differences["pitch_cents"] = (round(1200 * math.log2(second["pitch_hz"] / first["pitch_hz"]), 3)
                                  if first["pitch_hz"] and second["pitch_hz"] else None)
    differences["spectral_centroid_hz"] = (round(second["spectral_centroid_hz"] - first["spectral_centroid_hz"], 3)
        if first["spectral_centroid_hz"] is not None and second["spectral_centroid_hz"] is not None else None)
    differences["spectral_distance_db"] = (round(sum(abs(x-y) for x, y in zip(
        first["spectral_bands_db"], second["spectral_bands_db"])) / 16, 4)
        if first["spectral_bands_db"] is not None and second["spectral_bands_db"] is not None else None)
    gain = (sum(x*y for x, y in zip(a["samples"], b["samples"])) /
            sum(x*x for x in a["samples"])) if any(a["samples"]) else 0.0
    differences["fitted_gain_db"] = _db(abs(gain))
    differences["polarity_inverted"] = gain < 0
    differences["waveform_snr_db"] = _waveform_snr(a["samples"], b["samples"])
    differences["onset_aligned_snr_db"] = (_waveform_snr(a["samples"], b["samples"],
        shift_frames=round(differences["onset_ms"] * a["sample_rate"] * a["channels"] / 1000))
        if differences["onset_ms"] is not None else None)
    differences["gain_adjusted_snr_db"] = _waveform_snr(a["samples"], b["samples"], gain=gain) if gain else None
    differences["pcm_identical"] = a["pcm_sha256"] == b["pcm_sha256"]
    return {"format": {"sample_rate": a["sample_rate"], "channels": a["channels"]},
            "reference": first, "candidate": second, "difference": differences}


def judge(report: dict, expectation: dict) -> dict:
    """A declared signal relation, with all thresholds returned for audit."""
    kind = expectation["kind"]
    d = report["difference"]
    def within(key, target, tolerance):
        value = d.get(key)
        return value is not None and abs(value - target) <= tolerance
    if kind == "same":
        checks = {"duration_ms": within("duration_ms", 0, expectation.get("duration_tolerance_ms", 1)),
                  "waveform_snr_db": d["pcm_identical"] or (d["waveform_snr_db"] is not None and
                      d["waveform_snr_db"] >= expectation.get("min_snr_db", 70))}
    elif kind == "different":
        checks = {"maximum_similarity_rejected": not d["pcm_identical"] and
                  (d["waveform_snr_db"] is None or
                   d["waveform_snr_db"] < expectation.get("max_snr_db", 40))}
    elif kind == "gain_db":
        checks = {"level_change_db": within("rms_dbfs", expectation["value"], expectation.get("tolerance_db", 0.2)),
                  "polarity_preserved": not d["polarity_inverted"],
                  "shape_preserved": d["gain_adjusted_snr_db"] is not None and
                      d["gain_adjusted_snr_db"] >= expectation.get("min_shape_snr_db", 45)}
    elif kind == "pitch_semitones":
        checks = {"pitch_change_cents": within("pitch_cents", expectation["value"] * 100,
                                             expectation.get("tolerance_cents", 35)),
                  "duration_preserved": within("duration_ms", 0, expectation.get("duration_tolerance_ms", 20))}
    elif kind == "shift_ms":
        checks = {"onset_shift_ms": within("onset_ms", expectation["value"],
                                          expectation.get("tolerance_ms", 10)),
                  "waveform_shifted": d["onset_aligned_snr_db"] is not None and
                      d["onset_aligned_snr_db"] >= expectation.get("min_aligned_snr_db", 45)}
    elif kind == "pan_balance_db":
        checks = {"stereo_balance_change_db": within("stereo_balance_db", expectation["value"],
                                                     expectation.get("tolerance_db", 0.3))}
    else:
        raise ValueError(f"unknown audio expectation: {kind}")
    return {"expectation": expectation, "checks": checks, "passed": all(checks.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--expect", help='JSON rule, e.g. {"kind":"gain_db","value":-6}')
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = compare(args.reference, args.candidate)
    if args.expect:
        report["verdict"] = judge(report, json.loads(args.expect))
    serialized = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    raise SystemExit(0 if report.get("verdict", {}).get("passed", True) else 1)


if __name__ == "__main__":
    main()
