"""Detecção de atividade de voz (VAD) baseada em energia e thresholding seguro."""
from __future__ import annotations

import numpy as np


class EnergyVAD:
    """Filtro VAD baseado em energia com tolerância para trechos musicais/cantados."""

    def __init__(self, energy_threshold: float = 0.0005, enabled: bool = True) -> None:
        self.energy_threshold = energy_threshold
        self.enabled = enabled

    def has_speech(self, audio: np.ndarray) -> bool:
        """Retorna True se o áudio contém atividade vocal suficiente."""
        if not self.enabled:
            return True
        if len(audio) == 0:
            return False

        rms = float(np.sqrt(np.mean(np.square(audio))))
        return rms >= self.energy_threshold

