import math
import struct
import wave

from composer_rostrum.ear import evaluate_production


RATE = 8000


def write(path, values):
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        output.writeframes(b"".join(struct.pack("<h", round(32767 * max(-1, min(1, value))))
                                    for value in values))


def sine(frequency, gain=0.3, seconds=1):
    return [gain * math.sin(2 * math.pi * frequency * i / RATE)
            for i in range(round(seconds * RATE))]


def test_comp_identifies_source_in_each_segment_and_catches_bad_join(tmp_path):
    first, second, reference, good, wrong, click = (tmp_path / f"{name}.wav" for name in
                                                   ("first", "second", "reference", "good", "wrong", "click"))
    a, b = sine(200), sine(320)
    # Both sources cross zero at the splice, so the valid join is click-free.
    composite = a[:4000] + b[4000:]
    for path, values in ((first, a), (second, b), (reference, a), (good, composite),
                         (wrong, b[:4000] + a[4000:]),
                         (click, a[:4000] + [0.7] + b[4001:])):
        write(path, values)
    spec = {"kind": "comp", "segments": [
        {"start_ms": 0, "end_ms": 500, "source": str(first)},
        {"start_ms": 500, "end_ms": 1000, "source": str(second)}]}
    assert evaluate_production(reference, good, spec)["passed"]
    assert not evaluate_production(reference, wrong, spec)["passed"]
    bad = evaluate_production(reference, click, spec)
    assert not bad["checks"]["joins_smooth"]
    assert bad["checks"]["segment_0"] and bad["checks"]["segment_1"]


def test_timing_requires_each_transient_and_protected_audio(tmp_path):
    original, fixed, missing, altered = (tmp_path / f"{name}.wav" for name in
                                         ("original", "fixed", "missing", "altered"))
    def hits(times):
        samples = [0.0] * RATE
        for moment in times:
            start = round(moment * RATE / 1000)
            for offset in range(40):
                samples[start+offset] = 0.7 * (1-offset/40)
        return samples
    write(original, hits([200, 530, 800]))
    write(fixed, hits([200, 500, 800]))
    write(missing, hits([200, 800]))
    damaged = hits([200, 500, 800])
    damaged[round(.2*RATE)] *= 0.3
    write(altered, damaged)
    spec = {"kind": "timing", "expected_ms": [200, 500, 800],
            "protected_regions": [[190, 230], [790, 830]]}
    assert evaluate_production(original, fixed, spec)["passed"]
    assert not evaluate_production(original, missing, spec)["passed"]
    assert not evaluate_production(original, altered, spec)["passed"]


def test_noise_rule_requires_reduction_and_keeps_wanted_signal(tmp_path):
    original, clean, mute, unchanged = (tmp_path / f"{name}.wav" for name in
                                        ("original", "clean", "mute", "unchanged"))
    hum = sine(100, 0.08)
    wanted = [0.3 * math.sin(2*math.pi*280*i/RATE) if 1600 <= i < 6400 else 0
              for i in range(RATE)]
    write(original, [x+y for x, y in zip(hum, wanted)])
    write(clean, wanted)
    write(mute, [0] * RATE)
    write(unchanged, [x+y for x, y in zip(hum, wanted)])
    spec = {"kind": "noise_cleanup", "noise_windows": [[0, 200], [800, 1000]],
            "signal_windows": [[300, 700]], "min_signal_snr_db": 10}
    assert evaluate_production(original, clean, spec)["passed"]
    assert not evaluate_production(original, mute, spec)["passed"]
    assert not evaluate_production(original, unchanged, spec)["passed"]


def test_clip_gain_balances_each_clip_and_rejects_global_gain(tmp_path):
    original, balanced, global_gain, clipped = (tmp_path / f"{name}.wav" for name in
                                               ("original", "balanced", "global", "clipped"))
    quiet, loud = sine(200, 0.1, .5), sine(200, 0.4, .5)
    write(original, quiet + loud)
    write(balanced, [x*2 for x in quiet] + [x*.5 for x in loud])
    write(global_gain, [x*2 for x in quiet+loud])
    write(clipped, [x*9 for x in quiet] + [x*2 for x in loud])
    target = 20 * math.log10(.2 / math.sqrt(2))
    spec = {"kind": "clip_gain", "clips": [
        {"start_ms": 0, "end_ms": 500, "target_rms_dbfs": target},
        {"start_ms": 500, "end_ms": 1000, "target_rms_dbfs": target}]}
    assert evaluate_production(original, balanced, spec)["passed"]
    assert not evaluate_production(original, global_gain, spec)["passed"]
    assert not evaluate_production(original, clipped, spec)["passed"]
