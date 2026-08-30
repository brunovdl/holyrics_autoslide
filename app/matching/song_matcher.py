"""Identificação de música na playlist com base no rolling transcript."""
from __future__ import annotations

from dataclasses import dataclass
from rapidfuzz import fuzz

from app.models.song import Song, PlaylistSnapshot
from app.matching.normalizer import normalize_text
from app.utils.logging import log_event


@dataclass
class SongMatchResult:
    """Resultado da identificação de música."""
    song: Song | None
    score: float
    second_score: float
    margin: float
    is_confident: bool


class SongMatcher:
    """Compara o texto acumulado com todas as músicas da playlist usando pesos discriminativos."""

    def __init__(self, threshold: float = 88.0, min_margin: float = 10.0) -> None:
        self.threshold = threshold
        self.min_margin = min_margin

    def _build_playlist_word_frequency(self, playlist: PlaylistSnapshot) -> dict[str, int]:
        """Calcula em quantas músicas da playlist cada palavra ocorre (frequência de documento)."""
        freq: dict[str, int] = {}
        for s in playlist.songs:
            norm = s.normalized_full_text or normalize_text(s.full_text)
            words = set(w for w in norm.split() if len(w) > 2)
            for w in words:
                freq[w] = freq.get(w, 0) + 1
        return freq

    def identify_song(self, transcript: str, playlist: PlaylistSnapshot) -> SongMatchResult:
        """Avalia a playlist e retorna a música candidata mais provável com base em termos discriminativos."""
        normalized_transcript = normalize_text(transcript)
        if not normalized_transcript or not playlist.songs:
            return SongMatchResult(
                song=None,
                score=0.0,
                second_score=0.0,
                margin=0.0,
                is_confident=False,
            )

        transcript_words = set(w for w in normalized_transcript.split() if len(w) > 2)
        doc_freq = self._build_playlist_word_frequency(playlist)
        num_songs = len(playlist.songs)

        scored_songs: list[tuple[Song, float]] = []

        for song in playlist.songs:
            if not song.normalized_full_text:
                song.normalized_full_text = normalize_text(song.full_text)

            p_ratio = fuzz.partial_ratio(normalized_transcript, song.normalized_full_text)
            token_set = fuzz.token_set_ratio(normalized_transcript, song.normalized_full_text)
            base_score = (p_ratio * 0.55) + (token_set * 0.45)

            # Calcula bônus discriminativo positivo para palavras raras e exclusivas desta música
            song_words = set(w for w in song.normalized_full_text.split() if len(w) > 2)
            matched_words = transcript_words.intersection(song_words)

            rare_bonus = 0.0
            if matched_words:
                weights = []
                for w in matched_words:
                    freq = doc_freq.get(w, num_songs)
                    # Palavra exclusiva da música na playlist (freq == 1) recebe bônus máximo
                    if freq == 1:
                        weights.append(1.0)
                    elif freq == 2:
                        weights.append(0.5)
                if weights:
                    rare_bonus = min(12.0, (sum(weights) / max(1, len(matched_words))) * 12.0)

            # Bônus positivo aditivo: valoriza termos raros exclusivos sem nunca derrubar o score textual base
            final_song_score = min(100.0, base_score + rare_bonus)
            scored_songs.append((song, final_song_score))

        scored_songs.sort(key=lambda x: x[1], reverse=True)

        best_song, best_score = scored_songs[0]
        second_score = scored_songs[1][1] if len(scored_songs) > 1 else 0.0
        margin = best_score - second_score

        is_confident = (best_score >= self.threshold) and (margin >= self.min_margin or len(scored_songs) == 1)

        if is_confident:
            log_event(
                "MATCHER",
                f"Música identificada: '{best_song.title}' (Score: {best_score:.1f}%, Margem: {margin:.1f}%)",
            )

        return SongMatchResult(
            song=best_song if is_confident else None,
            score=round(best_score, 1),
            second_score=round(second_score, 1),
            margin=round(margin, 1),
            is_confident=is_confident,
        )

