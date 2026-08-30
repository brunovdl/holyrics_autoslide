"""Modelos de representação de slides de músicas."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SongSlide:
    """Slide original de uma música."""
    index: int  # 0-based
    text: str
    normalized_text: str = ""
    start_words: str = ""  # Primeiras palavras para antecipação


@dataclass
class SlideCandidate:
    """Candidato de slide avaliado pelo Matcher / Decision Engine."""
    slide_index: int
    score: float
    text: str
    is_repeated: bool = False
    context_bonus: float = 0.0

