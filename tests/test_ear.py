import math
import struct
import wave

from composer_rostrum.ear import compare, judge


def tone(path, *, frequency=220, gain=0.4, delay=0, left=1, right=1, missing_tail=False):
    rate = 48000
    frames = []
    for index in range(rate):
        time = (index - round(delay * rate)) / rate
        sample = gain * math.sin(2 * math.pi * frequency * time) if 0 <= time < 0.8 else 0.0
        if missing_tail and time > 0.4:
            sample = 0.0
        envelope = min(1.0, max(0.0, time / 0.01), max(0.0, (0.8-time) / 0.01))
        frames.append(struct.pack("<hh", round(32767 * sample * envelope * left),
                                  round(32767 * sample * envelope * right)))
    with wave.open(str(path), "wb") as output:
        output.setparams((2, 2, rate, 0, "NONE", "not compressed"))
        output.writeframes(b"".join(frames))


def test_same_gain_and_missing_audio_are_distinct(tmp_path):
    a, b, c = (tmp_path / name for name in ("a.wav", "b.wav", "c.wav"))
    tone(a)
    tone(b, gain=0.4 * 10 ** (-6 / 20))
    tone(c, missing_tail=True)
    same = compare(a, a)
    assert same["difference"]["pcm_identical"]
    assert judge(same, {"kind": "same"})["passed"]
    changed = compare(a, b)
    assert judge(changed, {"kind": "gain_db", "value": -6})["passed"]
    assert not judge(changed, {"kind": "same"})["passed"]
    lost = compare(a, c)
    assert not judge(lost, {"kind": "same"})["passed"]
    assert judge(lost, {"kind": "different"})["passed"]


def test_pitch_and_pan_have_independent_numeric_evidence(tmp_path):
    a, pitch, pan = (tmp_path / name for name in ("a.wav", "pitch.wav", "pan.wav"))
    tone(a)
    tone(pitch, frequency=440)
    tone(pan, left=0.5)
    pitch_report = compare(a, pitch)
    assert judge(pitch_report, {"kind": "pitch_semitones", "value": 12})["passed"]
    assert abs(pitch_report["difference"]["spectral_centroid_hz"] - 220) < 10
    assert pitch_report["difference"]["spectral_distance_db"] > 5
    assert not judge(pitch_report, {"kind": "same"})["passed"]
    pan_report = compare(a, pan)
    assert judge(pan_report, {"kind": "pan_balance_db", "value": 6.0206})["passed"]


def test_wrong_timing_is_visible(tmp_path):
    a, late = (tmp_path / name for name in ("a.wav", "late.wav"))
    tone(a)
    tone(late, delay=0.1)
    report = compare(a, late)
    assert abs(report["difference"]["onset_ms"] - 100) <= 10
    assert judge(report, {"kind": "shift_ms", "value": 100})["passed"]
    assert not judge(report, {"kind": "same"})["passed"]


def test_silent_reference_can_be_equal_or_different(tmp_path):
    silent, audible = (tmp_path / name for name in ("silent.wav", "audible.wav"))
    tone(silent, gain=0)
    tone(audible)
    assert judge(compare(silent, silent), {"kind": "same"})["passed"]
    assert judge(compare(silent, audible), {"kind": "different"})["passed"]


def test_antiphase_stereo_is_not_mistaken_for_silence(tmp_path):
    anti = tmp_path / "anti.wav"
    tone(anti, right=-1)
    report = compare(anti, anti)
    assert report["reference"]["active_windows"] > 0
    assert report["reference"]["rms_dbfs"] is not None
    assert judge(report, {"kind": "same"})["passed"]


def test_gain_rule_rejects_polarity_flip(tmp_path):
    a, inverted = (tmp_path / name for name in ("a.wav", "inverted.wav"))
    tone(a)
    tone(inverted, left=-1, right=-1)
    report = compare(a, inverted)
    assert report["difference"]["polarity_inverted"]
    assert not judge(report, {"kind": "gain_db", "value": 0})["passed"]
