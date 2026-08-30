"""Testes do pipeline de áudio, loopback, resampler e cálculo de VU meter."""
import numpy as np
import pytest

from app.audio.devices import list_audio_devices
from app.audio.loopback import LoopbackAudioSource
from app.audio.wav_source import WavFileAudioSource
from app.audio.resampler import (
    convert_to_mono,
    resample_audio,
    calculate_audio_levels,
    normalize_audio,
)


def test_list_audio_devices_spec_AC_008(monkeypatch: pytest.MonkeyPatch):
    """@spec:AC-008 — Enumeração detalhada de dispositivos de entrada de áudio."""
    import app.audio.devices as dev_module

    fake_devices = [
        {"name": "Microfone Realtek", "hostapi": 0, "max_input_channels": 2, "default_samplerate": 48000.0},
        {"name": "Speakers (Monitor)", "hostapi": 0, "max_input_channels": 2, "default_samplerate": 44100.0},
    ]
    fake_hostapis = [{"name": "ALSA"}]

    class FakeSoundDevice:
        @staticmethod
        def query_devices():
            return fake_devices

        @staticmethod
        def query_hostapis():
            return fake_hostapis

    monkeypatch.setattr(dev_module, "sd", FakeSoundDevice)
    devices = list_audio_devices()
    assert len(devices) == 2
    assert devices[0].name == "Microfone Realtek"
    assert devices[1].is_loopback is True


def test_loopback_source_spec_AC_009():
    """@spec:AC-009 — Captura de áudio da saída do sistema por Loopback."""
    source = LoopbackAudioSource(device_id=None)
    assert source.is_active() is False


def test_wav_audio_source_spec_AC_010(tmp_path):
    """@spec:AC-010 — Fonte de áudio simulada por arquivo WAV para testes."""
    from scipy.io import wavfile

    wav_file = tmp_path / "test.wav"
    sr = 16000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    sine = 0.5 * np.sin(2 * np.pi * 440 * t)
    wavfile.write(str(wav_file), sr, (sine * 32767).astype(np.int16))

    received_chunks = []

    def chunk_cb(chunk: np.ndarray):
        received_chunks.append(chunk)

    wav_source = WavFileAudioSource(
        file_path=wav_file,
        target_sample_rate=16000,
        chunk_duration=0.1,
        loop=False,
    )
    wav_source.start(chunk_cb)
    import time
    time.sleep(0.3)
    wav_source.stop()

    assert len(received_chunks) > 0
    assert isinstance(received_chunks[0], np.ndarray)


def test_audio_normalization_and_resampling_spec_AC_011():
    """@spec:AC-011 — Normalização, conversão para mono e reamostragem a 16 kHz."""
    stereo_audio = np.random.uniform(-0.5, 0.5, (48000, 2)).astype(np.float32)
    mono_audio = convert_to_mono(stereo_audio)
    assert mono_audio.ndim == 1
    assert len(mono_audio) == 48000

    audio_16k = resample_audio(mono_audio, orig_sr=48000, target_sr=16000)
    assert len(audio_16k) == 16000
    assert audio_16k.dtype == np.float32

    normalized = normalize_audio(audio_16k, target_peak=0.95)
    peak = np.max(np.abs(normalized))
    assert peak <= 1.0


def test_calculate_audio_levels_spec_AC_012():
    """@spec:AC-012 — Indicador visual de nível de áudio em tempo real."""
    silence = np.zeros(1600, dtype=np.float32)
    rms_db, peak_db = calculate_audio_levels(silence)
    assert rms_db == -60.0
    assert peak_db == -60.0

    t = np.linspace(0, 0.1, 1600, endpoint=False)
    sine = 0.8 * np.sin(2 * np.pi * 440 * t)
    rms_db, peak_db = calculate_audio_levels(sine.astype(np.float32))
    assert rms_db > -60.0
    assert peak_db > -60.0
    assert peak_db >= rms_db


def test_voice_bandpass_filter_attenuation():
    """Valida atenuação de frequências fora da banda vocal 300Hz-3400Hz."""
    from app.audio.resampler import apply_voice_bandpass_filter
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)

    # Tom de 60 Hz (grave / ruído elétrico) vs Tom de 1000 Hz (frequência central vocal)
    low_freq_tone = (0.8 * np.sin(2 * np.pi * 60 * t)).astype(np.float32)
    vocal_tone = (0.8 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)

    filtered_low = apply_voice_bandpass_filter(low_freq_tone, sample_rate=sr)
    filtered_vocal = apply_voice_bandpass_filter(vocal_tone, sample_rate=sr)

    low_energy = np.mean(filtered_low ** 2)
    vocal_energy = np.mean(filtered_vocal ** 2)

    assert low_energy < vocal_energy * 0.1
