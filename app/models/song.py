"""Modelos de representação de músicas e playlists do Holyrics."""
from __future__ import annotations

from dataclasses import dataclass, field
from app.models.slide import SongSlide


@dataclass
class Song:
    """Representação de uma música cadastrada na playlist."""
    id: str
    title: str
    artist: str = ""
    slides: list[SongSlide] = field(default_factory=list)
    full_text: str = ""
    normalized_full_text: str = ""

    @property
    def total_slides(self) -> int:
        return len(self.slides)


@dataclass
class PlaylistSnapshot:
    """Snapshot em memória da playlist do Holyrics."""
    songs: list[Song] = field(default_factory=list)
    last_updated: float = 0.0

    def get_song_by_id(self, song_id: str) -> Song | None:
        for s in self.songs:
            if str(s.id) == str(song_id):
                return s
        return None

