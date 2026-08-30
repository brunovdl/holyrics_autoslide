"""Interface abstrata para engines de transcrição de áudio."""
from __future__ import annotations

from abc import ABC, abstractmethod
import numpy as np
from app.models.transcription import TranscriptionResult


class TranscriptionEngine(ABC):
    """Interface desacoplada para reconhecimento automático de fala (ASR)."""

    @abstractmethod
    def load_model(self) -> None:
        """Carrega os pesos do modelo em memória."""
        pass

    @abstractmethod
    def transcribe(self, audio: np.ndarray, prompt: str | None = None) -> TranscriptionResult:
        """Transcreve um bloco de áudio (16 kHz, mono, float32) com vocabulário contextual opcional."""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Indica se o modelo está carregado e pronto para inferência."""
        pass

