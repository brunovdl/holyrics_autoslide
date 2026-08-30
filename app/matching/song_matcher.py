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
    """Compara o texto acumulado com todas as músicas da playlist."""

    def __init__(self, threshold: float = 82.0, min_margin: float = 8.0) -> None:
        self.threshold = threshold
        self.min_margin = min_margin

    def identify_song(self, transcript: str, playlist: PlaylistSnapshot) -> SongMatchResult:
        """Avalia a playlist e retorna a música candidata mais provável."""
        normalized_transcript = normalize_text(transcript)
        if not normalized_transcript or not playlist.songs:
            return SongMatchResult(
                song=None,
                score=0.0,
                second_score=0.0,
                margin=0.0,
                is_confident=False,
            )

        scored_songs: list[tuple[Song, float]] = []

        for song in playlist.songs:
            if not song.normalized_full_text:
                song.normalized_full_text = normalize_text(song.full_text)

            best_slide_score = 0.0
            for slide in song.slides:
                if not slide.normalized_text:
                    slide.normalized_text = normalize_text(slide.text)
                if slide.normalized_text:
                    s_score = fuzz.partial_ratio(normalized_transcript, slide.normalized_text)
                    if s_score > best_slide_score:
                        best_slide_score = s_score

            p_ratio = fuzz.partial_ratio(normalized_transcript, song.normalized_full_text)
            token_set = fuzz.token_set_ratio(normalized_transcript, song.normalized_full_text)

            combined_score = max(best_slide_score, (p_ratio * 0.60) + (token_set * 0.40))
            scored_songs.append((song, combined_score))

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

