"""Normalização de texto e de fala para fuzzy matching."""
from __future__ import annotations

import re
import unicodedata

SPEECH_CONTRACTIONS: dict[str, str] = {
    r"\bto\b": "estou",
    r"\bta\b": "esta",
    r"\btava\b": "estava",
    r"\bpra\b": "para",
    r"\bpras\b": "para as",
    r"\bpro\b": "para o",
    r"\bpros\b": "para os",
    r"\bnum\b": "em um",
    r"\bnuma\b": "em uma",
    r"\bvc\b": "voce",
    r"\bne\b": "nao e",
    r"\bdaqui\b": "de aqui",
}

PUNCTUATION_REGEX = re.compile(r"[^\w\s]", re.UNICODE)
WHITESPACE_REGEX = re.compile(r"\s+")


def remove_accents(text: str) -> str:
    """Remove acentos mantendo os caracteres base."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])


def normalize_text(text: str, expand_contractions: bool = True) -> str:
    """Normaliza o texto para matching de letras e transcrições."""
    if not text:
        return ""

    normalized = text.lower()
    normalized = remove_accents(normalized)
    normalized = PUNCTUATION_REGEX.sub(" ", normalized)

    if expand_contractions:
        for pattern, replacement in SPEECH_CONTRACTIONS.items():
            normalized = re.sub(pattern, replacement, normalized)

    normalized = WHITESPACE_REGEX.sub(" ", normalized).strip()
    return normalized

