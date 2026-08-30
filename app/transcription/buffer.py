"""Gerenciamento de buffer de áudio circular e janela deslizante de transcrição."""
from __future__ import annotations

import collections
import threading
import time
import numpy as np


class AudioRingBuffer:
    """Ring buffer circular seguro para desacoplar a captura de áudio do worker de transcrição."""

    def __init__(self, max_seconds: float = 30.0, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self.max_samples = int(max_seconds * sample_rate)
        self._buffer = np.zeros(self.max_samples, dtype=np.float32)
        self._write_pos = 0
        self._total_written = 0
        self._lock = threading.Lock()
        self.dropped_frames = 0

    @property
    def total_written(self) -> int:
        with self._lock:
            return self._total_written

    def write(self, chunk: np.ndarray) -> None:
        """Insere novas amostras no buffer circular."""
        with self._lock:
            chunk_len = len(chunk)
            if chunk_len > self.max_samples:
                chunk = chunk[-self.max_samples :]
                chunk_len = len(chunk)

            end_pos = self._write_pos + chunk_len
            if end_pos <= self.max_samples:
                self._buffer[self._write_pos : end_pos] = chunk
            else:
                first_part = self.max_samples - self._write_pos
                self._buffer[self._write_pos :] = chunk[:first_part]
                second_part = chunk_len - first_part
                self._buffer[:second_part] = chunk[first_part:]

            self._write_pos = (self._write_pos + chunk_len) % self.max_samples
            self._total_written += chunk_len

    def get_recent(self, seconds: float) -> np.ndarray:
        """Obtém as amostras dos últimos N segundos."""
        with self._lock:
            num_samples = min(int(seconds * self.sample_rate), self.max_samples)
            if self._total_written < num_samples:
                num_samples = self._total_written

            if num_samples == 0:
                return np.zeros(0, dtype=np.float32)

            start_pos = (self._write_pos - num_samples) % self.max_samples
            if start_pos + num_samples <= self.max_samples:
                return self._buffer[start_pos : start_pos + num_samples].copy()
            else:
                first_part = self.max_samples - start_pos
                second_part = num_samples - first_part
                return np.concatenate([self._buffer[start_pos:], self._buffer[:second_part]]).copy()


class RollingTranscriptBuffer:
    """Mantém o histórico textual acumulado das transcrições recentes."""

    def __init__(self, max_duration_seconds: float = 12.0) -> None:
        self.max_duration_seconds = max_duration_seconds
        self._entries: collections.deque[tuple[float, str]] = collections.deque()
        self._lock = threading.Lock()

    def add(self, text: str, timestamp: float | None = None) -> None:
        """Adiciona um trecho de texto transcrito."""
        if not text or not text.strip():
            return
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            self._entries.append((ts, text.strip()))
            self._prune(ts)

    def _prune(self, current_time: float | None = None) -> None:
        if not self._entries:
            return
        ref_time = current_time if current_time is not None else self._entries[-1][0]
        cutoff = ref_time - self.max_duration_seconds
        while self._entries and self._entries[0][0] < cutoff:
            self._entries.popleft()

    def get_text(self, current_time: float | None = None) -> str:
        """Retorna todo o texto acumulado na janela temporal."""
        with self._lock:
            if not self._entries:
                return ""
            self._prune(current_time)
            return " ".join([entry[1] for entry in self._entries])

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

