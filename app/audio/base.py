"""Interface abstrata para fontes de áudio."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable
import numpy as np


class AudioSource(ABC):
    """Interface base para captura ou simulação de áudio."""

    @abstractmethod
    def start(self, callback: Callable[[np.ndarray], None]) -> None:
        """Inicia a captura de áudio enviando blocos para o callback."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Interrompe a captura e libera os recursos de áudio."""
        pass

    @abstractmethod
    def is_active(self) -> bool:
        """Retorna se a fonte de áudio está capturando ativamente."""
        pass

