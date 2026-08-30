"""Utilitários de processamento de sinal, reamostragem e métricas de áudio."""
from __future__ import annotations

import math
import numpy as np

try:
    from scipy import signal
except ImportError:
    signal = None


def convert_to_mono(audio: np.ndarray) -> np.ndarray:
    """Converte array de áudio estéreo/multicanal para mono."""
    if audio.ndim == 1:
        return audio
    elif audio.ndim == 2:
        return np.mean(audio, axis=1)
    else:
        return np.mean(audio, axis=-1)


def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int = 16000) -> np.ndarray:
    """Reamostra o array de áudio para a taxa de amostragem alvo (padrão 16 kHz)."""
    if orig_sr == target_sr or len(audio) == 0:
        return audio.astype(np.float32)

    if signal is not None:
        num_target_samples = int(round(len(audio) * float(target_sr) / float(orig_sr)))
        resampled = signal.resample(audio, num_target_samples)
        return resampled.astype(np.float32)
    else:
        orig_indices = np.arange(len(audio))
        target_len = int(round(len(audio) * float(target_sr) / float(orig_sr)))
        target_indices = np.linspace(0, len(audio) - 1, target_len)
        resampled = np.interp(target_indices, orig_indices, audio)
        return resampled.astype(np.float32)


def calculate_audio_levels(audio: np.ndarray) -> tuple[float, float]:
    """Calcula nível RMS e Peak em decibéis (dBFS).

    Retorna: (rms_db, peak_db) com valor mínimo em -60 dBFS.
    """
    if len(audio) == 0:
        return -60.0, -60.0

    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(np.square(audio))))

    if peak > 0:
        peak_db = 20.0 * math.log10(peak)
    else:
        peak_db = -60.0

    if rms > 0:
        rms_db = 20.0 * math.log10(rms)
    else:
        rms_db = -60.0

    peak_db = max(-60.0, min(0.0, peak_db))
    rms_db = max(-60.0, min(0.0, rms_db))

    return round(rms_db, 1), round(peak_db, 1)


def normalize_audio(audio: np.ndarray, target_peak: float = 0.95) -> np.ndarray:
    """Normaliza o áudio com segurança evitando clipping."""
    peak = float(np.max(np.abs(audio)))
    if peak > 0.0001:
        scaling = min(target_peak / peak, 3.0)
        return (audio * scaling).astype(np.float32)
    return audio.astype(np.float32)


def apply_voice_bandpass_filter(
    audio: np.ndarray,
    sample_rate: int = 16000,
    lowcut: float = 300.0,
    highcut: float = 3400.0,
) -> np.ndarray:
    """Aplica filtro passa-faixa (300Hz-3400Hz) para destacar a voz cantante e atenuar graves/pratos."""
    if len(audio) < 64:
        return audio.astype(np.float32)

    if signal is not None:
        try:
            nyq = 0.5 * sample_rate
            low = max(0.01, lowcut / nyq)
            high = min(0.99, highcut / nyq)
            sos = signal.butter(4, [low, high], btype="bandpass", output="sos")
            filtered = signal.sosfiltfilt(sos, audio)
            return filtered.astype(np.float32)
        except Exception:
            return audio.astype(np.float32)
    return audio.astype(np.float32)

