"""Deduplicação e fusão de janelas de transcrição sobrepostas."""
from __future__ import annotations

import collections
import threading
import time
from app.matching.normalizer import normalize_text


class TranscriptToken:
    """Representa um token ou palavra com seu timestamp de emissão."""

    def __init__(self, raw: str, norm: str, timestamp: float) -> None:
        self.raw = raw
        self.norm = norm
        self.timestamp = timestamp


class TranscriptMerger:
    """Mescla transcrições de janelas sobrepostas eliminando repetições artificiais."""

    def __init__(self, max_history_seconds: float = 15.0) -> None:
        self.max_history_seconds = max_history_seconds
        self._tokens: collections.deque[TranscriptToken] = collections.deque()
        self._lock = threading.Lock()
        self.last_transcript_chunk = ""

    def add_transcription(self, text: str, timestamp: float | None = None) -> str:
        """Processa e funde uma nova transcrição, retornando o texto recente adicionado."""
        if not text or not text.strip():
            return ""

        ts = timestamp if timestamp is not None else time.time()
        self.last_transcript_chunk = text.strip()
        raw_words = text.strip().split()
        if not raw_words:
            return ""

        norm_words = [normalize_text(w) for w in raw_words]

        with self._lock:
            self._prune(ts)

            if not self._tokens:
                # Primeiro lote
                for rw, nw in zip(raw_words, norm_words):
                    if nw:
                        self._tokens.append(TranscriptToken(rw, nw, ts))
                return text.strip()

            # Procura a maior sobreposição entre o final dos tokens acumulados e o início dos novos tokens
            existing_norms = [t.norm for t in self._tokens]
            max_overlap = min(len(existing_norms), len(norm_words))
            best_overlap_len = 0

            for overlap_len in range(max_overlap, 0, -1):
                suffix = existing_norms[-overlap_len:]
                prefix = norm_words[:overlap_len]
                if suffix == prefix:
                    best_overlap_len = overlap_len
                    break

            # Se encontrou sobreposição, adiciona apenas os tokens posteriores
            new_tokens_to_add = raw_words[best_overlap_len:]
            new_norms_to_add = norm_words[best_overlap_len:]

            for rw, nw in zip(new_tokens_to_add, new_norms_to_add):
                if nw:
                    self._tokens.append(TranscriptToken(rw, nw, ts))

            added_text = " ".join(new_tokens_to_add)
            return added_text

    def _prune(self, current_time: float) -> None:
        cutoff = current_time - self.max_history_seconds
        while self._tokens and self._tokens[0].timestamp < cutoff:
            self._tokens.popleft()

    def get_window_text(self, duration_seconds: float = 4.0, current_time: float | None = None) -> str:
        """Recupera o texto deduplicado correspondente aos últimos N segundos."""
        with self._lock:
            if not self._tokens:
                return ""
            ref_time = current_time if current_time is not None else self._tokens[-1].timestamp
            self._prune(ref_time)
            cutoff = ref_time - duration_seconds
            recent_tokens = [t.raw for t in self._tokens if t.timestamp >= cutoff]
            return " ".join(recent_tokens)

    def get_slide_window_text(self, duration: float = 4.0) -> str:
        """Janela curta (3-5s) otimizada para resposta ágil de troca de slide."""
        return self.get_window_text(duration)

    def get_song_window_text(self, duration: float = 10.0) -> str:
        """Janela ampla (8-12s) com mais contexto para identificação segura de música."""
        return self.get_window_text(duration)

    def clear(self) -> None:
        """Limpa completamente todo o histórico ao trocar de música."""
        with self._lock:
            self._tokens.clear()
            self.last_transcript_chunk = ""
