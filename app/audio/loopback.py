"""Captura de áudio da saída do sistema (Loopback WASAPI / PulseAudio Monitor)."""
from __future__ import annotations

from typing import Callable
import numpy as np

from app.audio.base import AudioSource
from app.audio.capture import DeviceAudioSource
from app.audio.devices import get_default_device
from app.utils.logging import log_event


class LoopbackAudioSource(AudioSource):
    """Fonte de áudio que captura os sons emitidos pelos alto-falantes/fones."""

    def __init__(
        self,
        device_id: int | str | None = None,
        target_sample_rate: int = 16000,
        channel_selection: str = "mono",
        on_levels_update: Callable[[float, float], None] | None = None,
    ) -> None:
        self.device_id = device_id
        self.target_sample_rate = target_sample_rate
        self.channel_selection = channel_selection
        self.on_levels_update = on_levels_update
        self._source: DeviceAudioSource | None = None

    def start(self, callback: Callable[[np.ndarray], None]) -> None:
        resolved_id = self.device_id
        if resolved_id is None:
            dev = get_default_device("loopback")
            if dev:
                resolved_id = dev.id

        log_event("AUDIO", f"Iniciando captura Loopback no dispositivo ID: {resolved_id}")
        self._source = DeviceAudioSource(
            device_id=resolved_id,
            target_sample_rate=self.target_sample_rate,
            channel_selection=self.channel_selection,
            on_levels_update=self.on_levels_update,
        )
        self._source.start(callback)

    def stop(self) -> None:
        if self._source:
            self._source.stop()
            self._source = None

    def is_active(self) -> bool:
        return self._source.is_active() if self._source else False

