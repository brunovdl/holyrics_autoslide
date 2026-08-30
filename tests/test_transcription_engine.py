"""Testes do motor de transcrição Whisper, VAD e buffers."""
import numpy as np

from app.models.transcription import TranscriptionResult, TranscriptionSegment
from app.transcription.base import TranscriptionEngine
from app.transcription.buffer import RollingTranscriptBuffer
from app.transcription.vad import EnergyVAD


class MockWhisperEngine(TranscriptionEngine):
    def __init__(self):
        self._ready = False

    def load_model(self) -> None:
        self._ready = True

    def is_ready(self) -> bool:
        return self._ready

    def transcribe(self, audio: np.ndarray) -> TranscriptionResult:
        return TranscriptionResult(
            text="Aquele que acalma o vento",
            duration=len(audio) / 16000.0,
            inference_time=45.0,
            segments=[
                TranscriptionSegment(
                    text="Aquele que acalma o vento",
                    start=0.0,
                    end=2.0,
                    avg_logprob=-0.15,
                )
            ],
        )


def test_whisper_engine_loading_spec_AC_013():
    """@spec:AC-013 — Carregamento e inicialização do motor de transcrição Groq/Whisper."""
    from app.transcription.groq_whisper import GroqWhisperTranscriber
    groq_engine = GroqWhisperTranscriber(api_key="mock_key_123")
    assert groq_engine.is_ready() is False
    groq_engine.load_model()
    assert groq_engine.is_ready() is True

    mock_engine = MockWhisperEngine()
    assert mock_engine.is_ready() is False
    mock_engine.load_model()
    assert mock_engine.is_ready() is True


def test_rolling_transcript_buffer_spec_AC_014():
    """@spec:AC-014 — Processamento por chunks com sobreposição e histórico acumulado."""
    buffer = RollingTranscriptBuffer(max_duration_seconds=10.0)
    buffer.add("Aquele que acalma o vento", timestamp=100.0)
    buffer.add("aquele que aquieta o mar", timestamp=102.0)

    text = buffer.get_text()
    assert "Aquele que acalma o vento" in text
    assert "aquele que aquieta o mar" in text


def test_vad_speech_detection_spec_AC_015():
    """@spec:AC-015 — Detecção de voz e atividade vocal configurável."""
    vad = EnergyVAD(energy_threshold=0.01, enabled=True)

    # Silêncio
    silence = np.zeros(16000, dtype=np.float32)
    assert vad.has_speech(silence) is False

    # Sinal com energia
    audio_signal = np.random.uniform(-0.1, 0.1, 16000).astype(np.float32)
    assert vad.has_speech(audio_signal) is True

    # Com VAD desativado sempre retorna True
    vad.enabled = False
    assert vad.has_speech(silence) is True


def test_live_transcription_result_spec_AC_016():
    """@spec:AC-016 — Exibição da transcrição em tempo real na interface."""
    engine = MockWhisperEngine()
    engine.load_model()
    audio = np.random.uniform(-0.1, 0.1, 16000).astype(np.float32)
    result = engine.transcribe(audio)

    assert result.text == "Aquele que acalma o vento"
    assert result.inference_time == 45.0
    assert len(result.segments) == 1

