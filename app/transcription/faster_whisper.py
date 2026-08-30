"""Implementação do FasterWhisperTranscriber utilizando faster-whisper local."""
from __future__ import annotations

import time
import numpy as np

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

from app.transcription.base import TranscriptionEngine
from app.models.transcription import TranscriptionResult, TranscriptionSegment
from app.utils.logging import log_event


class FasterWhisperTranscriber(TranscriptionEngine):
    """Engine de transcrição local usando faster-whisper com inferência em CPU/CUDA."""

    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "auto",
        language: str = "pt",
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._model: WhisperModel | None = None
        self._is_ready = False

    def load_model(self) -> None:
        if WhisperModel is None:
            raise RuntimeError("Biblioteca faster-whisper não está instalada.")

        resolved_device = self.device
        if resolved_device == "auto":
            resolved_device = "cpu"

        resolved_compute = self.compute_type
        if resolved_compute == "auto":
            resolved_compute = "int8" if resolved_device == "cpu" else "float16"

        log_event(
            "ASR",
            f"Carregando modelo Whisper ({self.model_size}, device={resolved_device}, compute={resolved_compute})...",
        )
        t0 = time.time()
        import os
        threads = min(4, os.cpu_count() or 4)
        self._model = WhisperModel(
            self.model_size,
            device=resolved_device,
            compute_type=resolved_compute,
            cpu_threads=threads,
            num_workers=1,
            download_root=None,
        )
        self._is_ready = True
        elapsed = round(time.time() - t0, 2)
        log_event("ASR", f"Modelo Whisper pronto em {elapsed}s (threads={threads}).")

    def is_ready(self) -> bool:
        return self._is_ready

    def transcribe(self, audio: np.ndarray, prompt: str | None = None) -> TranscriptionResult:
        if not self._is_ready or self._model is None:
            raise RuntimeError("Modelo Faster-Whisper ainda não foi carregado.")

        if len(audio) == 0:
            return TranscriptionResult(text="", duration=0.0)

        duration = len(audio) / 16000.0
        t0 = time.time()

        segments_gen, _info = self._model.transcribe(
            audio,
            language=self.language if self.language != "auto" else None,
            beam_size=1,
            condition_on_previous_text=False,
            vad_filter=False,
            initial_prompt=prompt,
        )

        segments: list[TranscriptionSegment] = []
        text_parts: list[str] = []
        avg_logprobs: list[float] = []

        for seg in segments_gen:
            text_parts.append(seg.text.strip())
            avg_logprobs.append(seg.avg_logprob)
            segments.append(
                TranscriptionSegment(
                    text=seg.text.strip(),
                    start=seg.start,
                    end=seg.end,
                    avg_logprob=seg.avg_logprob,
                    no_speech_prob=seg.no_speech_prob,
                )
            )

        inference_time = (time.time() - t0) * 1000.0
        full_text = " ".join(text_parts).strip()
        mean_logprob = float(np.mean(avg_logprobs)) if avg_logprobs else 0.0

        return TranscriptionResult(
            text=full_text,
            avg_logprob=mean_logprob,
            duration=duration,
            inference_time=round(inference_time, 1),
            segments=segments,
        )

