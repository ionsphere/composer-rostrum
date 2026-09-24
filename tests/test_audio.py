import math
import struct
import wave
from pathlib import Path
import pytest
from composer_rostrum.audio import analyze_wav, write_fixture


@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_pcm_widths_and_silence(tmp_path, width):
    path = tmp_path / "silence.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setparams((2, width, 48000, 0, "NONE", "not compressed"))
        wav.writeframes((b"\x80" if width == 1 else bytes(width)) * 200)
    result = analyze_wav(path)
    assert result["silent"] and result["rms"] == 0 and result["rms_dbfs"] is None
    assert result["frames"] == 100


def test_measurements_and_hash_are_deterministic(tmp_path):
    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        wav.writeframes(struct.pack("<hhhh", 16384, -16384, 16384, -16384))
    result = analyze_wav(path)
    assert result["rms"] == 0.5 and result["peak"] == 0.5
    assert result["rms_dbfs"] == pytest.approx(-6.020599913)
    assert result == analyze_wav(path)


def test_truncated_wav_is_rejected(tmp_path):
    path = tmp_path / "fixture.wav"
    write_fixture(path, 0.1)
    path.write_bytes(path.read_bytes()[:-8])
    with pytest.raises(ValueError, match="truncated"):
        analyze_wav(path)


def test_procedural_fixture_is_non_silent_and_reproducible(tmp_path):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    write_fixture(a, 0.1)
    write_fixture(b, 0.1)
    assert a.read_bytes() == b.read_bytes()
    assert not analyze_wav(a)["silent"]


def test_audio_hash_ignores_container_metadata(tmp_path):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    write_fixture(a, 0.1)
    original = a.read_bytes()
    chunk = b"JUNK" + struct.pack("<I", 4) + b"test"
    b.write_bytes(original[:4] + struct.pack("<I", len(original)+len(chunk)-8) + original[8:] + chunk)
    first, second = analyze_wav(a), analyze_wav(b)
    assert first["content_hash"] != second["content_hash"]
    assert first["pcm_hash"] == second["pcm_hash"]
