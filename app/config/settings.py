"""Gerenciamento e persistência de configurações do sistema."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field

from app.config.defaults import (
    DEFAULT_HOLYRICS_HOST,
    DEFAULT_HOLYRICS_PORT,
    DEFAULT_HOLYRICS_TOKEN,
    DEFAULT_AUDIO_SOURCE_TYPE,
    DEFAULT_CHUNK_DURATION,
    DEFAULT_OVERLAP_DURATION,
    DEFAULT_ROLLING_WINDOW_DURATION,
    DEFAULT_GROQ_API_KEY,
    DEFAULT_GROQ_MODEL,
    DEFAULT_GROQ_BASE_URL,
    DEFAULT_WHISPER_LANGUAGE,
    DEFAULT_VAD_ENABLED,
    DEFAULT_SONG_THRESHOLD,
    DEFAULT_SONG_MARGIN,
    DEFAULT_SLIDE_THRESHOLD_STRONG,
    DEFAULT_SLIDE_THRESHOLD_POSSIBLE,
    DEFAULT_CONSECUTIVE_CONFIRMATIONS,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_MANUAL_PAUSE_SECONDS,
    DEFAULT_ANTICIPATION_MODE,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PLAYLIST_POLL_INTERVAL,
)

CONFIG_FILE_PATH = Path.home() / ".holyrics_autoslide_settings.json"


class HolyricsSettings(BaseModel):
    """Configurações de conexão com o Holyrics API Server."""
    host: str = Field(default=DEFAULT_HOLYRICS_HOST)
    port: int = Field(default=DEFAULT_HOLYRICS_PORT)
    token: str = Field(default=DEFAULT_HOLYRICS_TOKEN)
    timeout: float = Field(default=DEFAULT_HTTP_TIMEOUT)
    poll_interval: float = Field(default=DEFAULT_POLL_INTERVAL)
    playlist_poll_interval: float = Field(default=DEFAULT_PLAYLIST_POLL_INTERVAL)


class AudioSettings(BaseModel):
    """Configurações da captura e pipeline de áudio."""
    source_type: Literal["microphone", "loopback", "wav"] = Field(default=DEFAULT_AUDIO_SOURCE_TYPE)
    device_id: int | str | None = Field(default=None)
    device_name: str | None = Field(default=None)
    wav_file_path: str | None = Field(default=None)
    sample_rate: int = Field(default=16000)
    channels: int = Field(default=1)
    chunk_duration: float = Field(default=DEFAULT_CHUNK_DURATION)
    overlap_duration: float = Field(default=DEFAULT_OVERLAP_DURATION)
    rolling_window_duration: float = Field(default=DEFAULT_ROLLING_WINDOW_DURATION)


class TranscriptionSettings(BaseModel):
    """Configurações da API Groq Cloud e transcrição."""
    groq_api_key: str = Field(default=DEFAULT_GROQ_API_KEY)
    groq_model: str = Field(default=DEFAULT_GROQ_MODEL)
    groq_base_url: str = Field(default=DEFAULT_GROQ_BASE_URL)
    model: str = Field(default=DEFAULT_GROQ_MODEL)
    language: str = Field(default=DEFAULT_WHISPER_LANGUAGE)
    device: str = Field(default="cloud")
    compute_type: str = Field(default="api")
    vad_enabled: bool = Field(default=DEFAULT_VAD_ENABLED)


class DecisionSettings(BaseModel):
    """Configurações do motor de decisão e histerese."""
    song_threshold: float = Field(default=DEFAULT_SONG_THRESHOLD)
    song_margin: float = Field(default=DEFAULT_SONG_MARGIN)
    slide_threshold_strong: float = Field(default=DEFAULT_SLIDE_THRESHOLD_STRONG)
    slide_threshold_possible: float = Field(default=DEFAULT_SLIDE_THRESHOLD_POSSIBLE)
    consecutive_confirmations: int = Field(default=DEFAULT_CONSECUTIVE_CONFIRMATIONS)
    cooldown_seconds: float = Field(default=DEFAULT_COOLDOWN_SECONDS)
    manual_pause_seconds: float = Field(default=DEFAULT_MANUAL_PAUSE_SECONDS)
    anticipation_mode: Literal["conservador", "equilibrado", "antecipado"] = Field(
        default=DEFAULT_ANTICIPATION_MODE
    )


class AppSettings(BaseModel):
    """Configuração global persistente da aplicação."""
    holyrics: HolyricsSettings = Field(default_factory=HolyricsSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    transcription: TranscriptionSettings = Field(default_factory=TranscriptionSettings)
    decision: DecisionSettings = Field(default_factory=DecisionSettings)

    def save(self, file_path: Path = CONFIG_FILE_PATH) -> None:
        """Salva as configurações em arquivo JSON."""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(self.model_dump_json(indent=2))
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}")

    @classmethod
    def load(cls, file_path: Path = CONFIG_FILE_PATH) -> AppSettings:
        """Carrega as configurações salvas ou retorna os padrões."""
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls.model_validate(data)
            except Exception as e:
                print(f"Erro ao carregar configurações: {e}. Usando padrões.")
        return cls()

