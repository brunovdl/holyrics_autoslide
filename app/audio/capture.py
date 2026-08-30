"""Captura contínua de áudio via sounddevice."""
from __future__ import annotations

from typing import Callable
import numpy as np

try:
    import sounddevice as sd
except Exception:
    sd = None

from app.audio.base import AudioSource
from app.audio.resampler import calculate_audio_levels, convert_to_mono, resample_audio
from app.utils.logging import log_event


class DeviceAudioSource(AudioSource):
    """Fonte de captura para microfones e entradas físicas ou lógicas."""

    def __init__(
        self,
        device_id: int | str | None = None,
        target_sample_rate: int = 16000,
        chunk_samples: int = 1600,
        on_levels_update: Callable[[float, float], None] | None = None,
    ) -> None:
        self.device_id = device_id
        self.target_sample_rate = target_sample_rate
        self.chunk_samples = chunk_samples
        self.on_levels_update = on_levels_update
        self._stream: sd.InputStream | None = None
        self._is_active = False
        self._callback: Callable[[np.ndarray], None] | None = None

    def start(self, callback: Callable[[np.ndarray], None]) -> None:
        if sd is None:
            raise RuntimeError("Biblioteca sounddevice não está disponível no sistema.")

        self._callback = callback
        self._is_active = True

        dev_info = sd.query_devices(self.device_id) if self.device_id is not None else sd.query_devices(kind="input")
        native_sr = int(dev_info.get("default_samplerate", 44100))
        max_in = int(dev_info.get("max_input_channels", 0))
        channels = max_in if max_in > 0 else 2

        def _sd_callback(indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags) -> None:
            if not self._is_active:
                return

            audio_mono = convert_to_mono(indata.copy())
            if audio_mono.dtype != np.float32:
                audio_mono = audio_mono.astype(np.float32)

            rms_db, peak_db = calculate_audio_levels(audio_mono)
            if self.on_levels_update:
                self.on_levels_update(rms_db, peak_db)

            if native_sr != self.target_sample_rate:
                audio_16k = resample_audio(audio_mono, native_sr, self.target_sample_rate)
            else:
                audio_16k = audio_mono

            if self._callback:
                self._callback(audio_16k)

        try:
            self._stream = sd.InputStream(
                device=self.device_id,
                samplerate=native_sr,
                channels=channels,
                dtype="float32",
                callback=_sd_callback,
            )
            self._stream.start()
        except Exception:
            # Fallback para 1 canal caso o dispositivo recuse 2 canais
            self._stream = sd.InputStream(
                device=self.device_id,
                samplerate=native_sr,
                channels=1,
                dtype="float32",
                callback=_sd_callback,
            )
            self._stream.start()

        log_event("AUDIO", f"Captura iniciada no dispositivo: {dev_info.get('name')} ({native_sr} Hz)")

    def stop(self) -> None:
        self._is_active = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                log_event("AUDIO", f"Erro ao fechar stream de áudio: {e}", level=30)
            self._stream = None
        log_event("AUDIO", "Captura de áudio finalizada.")

    def is_active(self) -> bool:
        return self._is_active

