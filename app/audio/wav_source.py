"""Fonte de áudio baseada em arquivo WAV para testes e desenvolvimento."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable
import numpy as np

try:
    from scipy.io import wavfile
except ImportError:
    wavfile = None

from app.audio.base import AudioSource
from app.audio.resampler import calculate_audio_levels, convert_to_mono, resample_audio
from app.utils.logging import log_event


class WavFileAudioSource(AudioSource):
    """Fonte de áudio que simula streaming em tempo real a partir de um arquivo WAV."""

    def __init__(
        self,
        file_path: str | Path,
        target_sample_rate: int = 16000,
        chunk_duration: float = 0.1,
        loop: bool = True,
        on_levels_update: Callable[[float, float], None] | None = None,
    ) -> None:
        self.file_path = Path(file_path)
        self.target_sample_rate = target_sample_rate
        self.chunk_duration = chunk_duration
        self.loop = loop
        self.on_levels_update = on_levels_update
        self._is_active = False
        self._thread: threading.Thread | None = None

    def start(self, callback: Callable[[np.ndarray], None]) -> None:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Arquivo WAV não encontrado: {self.file_path}")

        if wavfile is None:
            raise RuntimeError("scipy.io.wavfile não está disponível.")

        sample_rate, data = wavfile.read(str(self.file_path))

        if data.dtype == np.int16:
            audio = data.astype(np.float32) / 32768.0
        elif data.dtype == np.int32:
            audio = data.astype(np.float32) / 2147483648.0
        elif data.dtype == np.uint8:
            audio = (data.astype(np.float32) - 128.0) / 128.0
        else:
            audio = data.astype(np.float32)

        audio_mono = convert_to_mono(audio)
        if sample_rate != self.target_sample_rate:
            audio_16k = resample_audio(audio_mono, sample_rate, self.target_sample_rate)
        else:
            audio_16k = audio_mono

        self._is_active = True
        chunk_samples = int(self.chunk_duration * self.target_sample_rate)

        def _play_loop() -> None:
            log_event("AUDIO", f"Reprodução de arquivo WAV iniciada: {self.file_path.name}")
            pos = 0
            total_samples = len(audio_16k)

            while self._is_active:
                start_time = time.time()
                end_pos = pos + chunk_samples
                if end_pos > total_samples:
                    if self.loop:
                        chunk = np.concatenate([audio_16k[pos:], audio_16k[: end_pos - total_samples]])
                        pos = end_pos - total_samples
                    else:
                        chunk = audio_16k[pos:]
                        self._is_active = False
                else:
                    chunk = audio_16k[pos:end_pos]
                    pos = end_pos

                if len(chunk) > 0:
                    rms_db, peak_db = calculate_audio_levels(chunk)
                    if self.on_levels_update:
                        self.on_levels_update(rms_db, peak_db)
                    callback(chunk)

                elapsed = time.time() - start_time
                sleep_time = max(0.0, self.chunk_duration - elapsed)
                time.sleep(sleep_time)

            log_event("AUDIO", "Reprodução de arquivo WAV finalizada.")

        self._thread = threading.Thread(target=_play_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._is_active = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def is_active(self) -> bool:
        return self._is_active

