"""Módulo unificado LyricsMatcher."""
from __future__ import annotations

from app.matching.song_matcher import SongMatcher, SongMatchResult
from app.matching.slide_matcher import SlideMatcher, SlideMatchResult
from app.models.song import Song, PlaylistSnapshot


class LyricsMatcher:
    """Orquestrador de matching para identificação de músicas e slides."""

    def __init__(
        self,
        song_threshold: float = 82.0,
        song_margin: float = 8.0,
        anticipation_mode: str = "equilibrado",
    ) -> None:
        self.song_matcher = SongMatcher(threshold=song_threshold, min_margin=song_margin)
        self.slide_matcher = SlideMatcher()
        self.anticipation_mode = anticipation_mode

    def match_song(self, transcript: str, playlist: PlaylistSnapshot) -> SongMatchResult:
        """Identifica a música na playlist."""
        return self.song_matcher.identify_song(transcript, playlist)

    def match_slide(
        self,
        transcript: str,
        song: Song,
        current_slide_index: int | None = None,
        recent_transcript: str = "",
    ) -> SlideMatchResult:
        """Identifica o slide dentro da música."""
        return self.slide_matcher.match_slide(
            transcript=transcript,
            song=song,
            current_slide_index=current_slide_index,
            anticipation_mode=self.anticipation_mode,
            recent_transcript=recent_transcript,
        )

