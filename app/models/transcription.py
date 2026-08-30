"""Modelos de dados de transcrição em tempo real."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TranscriptionSegment:
    """Segmento individual de transcrição gerado pelo Whisper."""
    text: str
    start: float
    end: float
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0


@dataclass
class TranscriptionResult:
    """Resultado consolidado de um bloco de transcrição."""
    text: str
    timestamp: float = field(default_factory=time.time)
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0
    duration: float = 0.0
    inference_time: float = 0.0
    segments: list[TranscriptionSegment] = field(default_factory=list)

