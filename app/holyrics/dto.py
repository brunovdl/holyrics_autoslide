from typing import Any
from pydantic import BaseModel, Field, field_validator


class HolyricsPlaylistItemDTO(BaseModel):
    """Item da lista retornada por GetLyricsPlaylist."""
    id: str | int
    title: str = ""
    artist: str = ""

    model_config = {"extra": "ignore"}


class HolyricsSlideItemDTO(BaseModel):
    """Item de slide retornado por GetLyrics."""
    text: str = ""

    @field_validator("text", mode="before")
    @classmethod
    def parse_text(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, dict):
            for k in ["text", "paragraph", "content", "lyrics", "verse", "words", "body", "label"]:
                if k in v and v[k]:
                    if isinstance(v[k], list):
                        return "\n".join(str(x) for x in v[k] if x).strip()
                    return str(v[k]).strip()
        return str(v).strip() if v else ""

    model_config = {"extra": "ignore"}


class HolyricsSongDetailsDTO(BaseModel):
    """Resposta de GetLyrics."""
    id: str | int | None = None
    title: str = ""
    artist: str = ""
    slides: list[HolyricsSlideItemDTO] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


class HolyricsCurrentPresentationDTO(BaseModel):
    """Resposta de GetCurrentPresentation."""
    id: str | int | None = None
    title: str | None = None
    artist: str | None = None
    slide: int | None = None  # Geralmente 1-based ou pode variar
    total_slides: int | None = None
    is_active: bool = True

    model_config = {"extra": "ignore"}

