"""Modelo de estado global da aplicação Holyrics AutoSlide."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from app.models.song import Song, PlaylistSnapshot


@dataclass
class AppState:
    """Estado unificado e reativo da aplicação."""
    # Status de conectividade e serviços
    holyrics_connected: bool = False
    holyrics_status: Literal["DESCONECTADO", "OCIOSO", "PROJETANDO"] = "DESCONECTADO"
    audio_capturing: bool = False
    transcriber_ready: bool = False
    automation_mode: Literal["PARADO", "MONITOR", "AUTOMATICO"] = "PARADO"
    manual_override_active: bool = False
    manual_override_remaining: float = 0.0

    # Apresentação e Dados Atuais
    playlist: PlaylistSnapshot = field(default_factory=PlaylistSnapshot)
    current_song: Song | None = None
    current_slide_index: int | None = None  # 0-based
    current_slide_number: int | None = None  # 1-based (para UI)
    total_slides: int = 0
    current_slide_text: str = ""

    # Decisão e Candidato
    candidate_slide_index: int | None = None
    candidate_slide_text: str = ""
    candidate_score: float = 0.0
    candidate_hits: int = 0
    required_hits: int = 2

    # Áudio & VU
    audio_rms_db: float = -60.0
    audio_peak_db: float = -60.0
    audio_dropped_frames: int = 0

    # Transcrição & Métricas
    last_transcript_chunk: str = ""
    rolling_transcript: str = ""
    inference_time_ms: float = 0.0
    rtf: float = 0.0  # Real-time factor
    total_slides_switched: int = 0
    total_slides_blocked: int = 0

    # Listeners de UI
    _listeners: list[Callable[[AppState], None]] = field(default_factory=list, repr=False)

    def add_listener(self, listener: Callable[[AppState], None]) -> None:
        """Adiciona um observador para receber notificações de mudanças de estado."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[AppState], None]) -> None:
        """Remove um observador de estado."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def notify(self) -> None:
        """Notifica todos os ouvintes sobre alterações no estado."""
        for listener in self._listeners:
            try:
                listener(self)
            except Exception:
                pass

