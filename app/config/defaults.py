"""Valores padrão e constantes do Holyrics AutoSlide carregados via ambiente/dotenv."""
from __future__ import annotations

import os
from dotenv import load_dotenv

# Carrega arquivo .env se presente
load_dotenv()

# Holyrics API Server
DEFAULT_HOLYRICS_HOST = os.getenv("HOLYRICS_HOST", "127.0.0.1")
DEFAULT_HOLYRICS_PORT = int(os.getenv("HOLYRICS_PORT", "8091"))
DEFAULT_HOLYRICS_TOKEN = os.getenv("HOLYRICS_TOKEN", "")
DEFAULT_HTTP_TIMEOUT = float(os.getenv("HOLYRICS_TIMEOUT", "2.0"))
DEFAULT_POLL_INTERVAL = 0.5
DEFAULT_PLAYLIST_POLL_INTERVAL = 3.0

# Áudio
DEFAULT_AUDIO_SOURCE_TYPE = "loopback"  # "microphone", "loopback", "wav"
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_AUDIO_CHANNELS = 1
DEFAULT_CHUNK_DURATION = 0.8  # segundos (latência ultra-baixa com Groq)
DEFAULT_OVERLAP_DURATION = 0.2  # segundos
DEFAULT_ROLLING_WINDOW_DURATION = 8.0  # segundos

# Transcrição (Groq Cloud Whisper API)
DEFAULT_GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL", "whisper-large-v3-turbo")
DEFAULT_GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
DEFAULT_WHISPER_LANGUAGE = "pt"
DEFAULT_VAD_ENABLED = True

# Heurística e Decisão
DEFAULT_SONG_THRESHOLD = 75.0
DEFAULT_SONG_MARGIN = 5.0
DEFAULT_SLIDE_THRESHOLD_STRONG = 78.0
DEFAULT_SLIDE_THRESHOLD_POSSIBLE = 68.0
DEFAULT_CONSECUTIVE_CONFIRMATIONS = 2
DEFAULT_COOLDOWN_SECONDS = 0.4
DEFAULT_MANUAL_PAUSE_SECONDS = 5.0
DEFAULT_ANTICIPATION_MODE = "equilibrado"  # "conservador", "equilibrado", "antecipado"

