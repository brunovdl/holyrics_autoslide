"""Agendador de inferência ASR baseado em amostras reais de áudio novo."""
from __future__ import annotations

import numpy as np
from app.transcription.buffer import AudioRingBuffer


class ChunkScheduler:
    """Controla o avanço temporal de inferência ASR baseado em amostras reais de áudio.

    Janela ASR: 2.5s (duração total enviada para o Whisper ter contexto acústico)
    Hop: 0.8s (intervalo de avanço de áudio inédito entre duas inferências)
    """

    def __init__(
        self,
        ring_buffer: AudioRingBuffer,
        window_duration: float = 2.5,
        hop_duration: float = 0.8,
        sample_rate: int = 16000,
    ) -> None:
        self.ring_buffer = ring_buffer
        self.window_duration = window_duration
        self.hop_duration = hop_duration
        self.sample_rate = sample_rate
        self.hop_samples = int(hop_duration * sample_rate)
        self._last_processed_total = ring_buffer.total_written
        self.dropped_chunks = 0

    def has_new_chunk(self) -> bool:
        """Verifica se acumulamos ao menos hop_samples de áudio novo desde a última inferência."""
        current_total = self.ring_buffer.total_written
        return (current_total - self._last_processed_total) >= self.hop_samples

    def get_chunk_for_inference(self) -> np.ndarray | None:
        """Recupera a janela de áudio para inferência e avança o contador de amostras processadas.
        
        Aplica política de backpressure 'latest wins' para descartar áudio velho se o ASR atrasar.
        """
        current_total = self.ring_buffer.total_written
        diff = current_total - self._last_processed_total
        if diff < self.hop_samples:
            return None

        # Contabiliza hops descartados se houve atraso superior a 1 hop
        dropped_hops = max(0, int(diff // self.hop_samples) - 1)
        self.dropped_chunks += dropped_hops

        # Política 'latest wins': entrega o áudio do presente e consome todo o backlog
        self._last_processed_total = current_total

        return self.ring_buffer.get_recent(self.window_duration)

    def reset(self) -> None:
        """Zera a posição do agendador."""
        self._last_processed_total = self.ring_buffer.total_written
        self.dropped_chunks = 0
