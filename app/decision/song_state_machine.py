"""Máquina de estados para governar o ciclo de vida e travamento da música ativa."""
from __future__ import annotations

import enum
import time
from app.models.song import Song


class SongState(str, enum.Enum):
    """Estados formais do ciclo de vida da música ativa."""
    SEARCHING_SONG = "SEARCHING_SONG"
    SONG_CANDIDATE = "SONG_CANDIDATE"
    SONG_LOCKED = "SONG_LOCKED"
    SONG_TRANSITION_CANDIDATE = "SONG_TRANSITION_CANDIDATE"


class SongStateMachine:
    """Controla o travamento e transições da música ativa, evitando trocas espúrias."""

    def __init__(self) -> None:
        self.state: SongState = SongState.SEARCHING_SONG
        self.locked_song: Song | None = None
        self.candidate_song: Song | None = None
        self.candidate_hits: int = 0
        self.candidate_started_at: float = 0.0
        self.last_state_change: float = time.time()

    def set_locked_song(self, song: Song) -> None:
        """Trava diretamente uma música (ex: vinda do Holyrics ou seleção manual)."""
        self.locked_song = song
        self.state = SongState.SONG_LOCKED
        self.candidate_song = None
        self.candidate_hits = 0
        self.candidate_started_at = 0.0
        self.last_state_change = time.time()

    def clear(self) -> None:
        """Reseta a máquina de estados para busca inicial."""
        self.state = SongState.SEARCHING_SONG
        self.locked_song = None
        self.candidate_song = None
        self.candidate_hits = 0
        self.candidate_started_at = 0.0
        self.last_state_change = time.time()

    def is_locked(self) -> bool:
        """Retorna True se uma música estiver fixada e travada."""
        return self.state == SongState.SONG_LOCKED and self.locked_song is not None
