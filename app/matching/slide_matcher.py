"""Identificação contextual de slides com resolução de refrões e antecipação."""
from __future__ import annotations

from dataclasses import dataclass
from rapidfuzz import fuzz

from app.models.song import Song
from app.models.slide import SlideCandidate
from app.matching.normalizer import normalize_text


STOPWORDS = {
    "e", "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "por", "pelo", "pela", "pelos", "pelas", "com", "sem",
    "para", "pra", "pro", "pras", "pros", "que", "se", "eu", "tu", "ele", "ela", "nos", "vos",
    "eles", "elas", "me", "te", "lhe", "lhes", "meu", "minha", "teu", "tua", "seu", "sua",
    "nosso", "nossa", "isso", "isto", "aquilo", "este", "esta", "esse", "essa", "aquele",
    "aquela", "ja", "mais", "mas", "bem", "como", "quando", "onde", "quem", "nao", "sim", "vai"
}


@dataclass
class SlideMatchResult:
    """Resultado da avaliação de slides."""
    best_candidate: SlideCandidate | None
    candidates: list[SlideCandidate]
    is_anticipation: bool = False


class SlideMatcher:
    """Calcula similaridade textual e bônus contextuais para os slides de uma música."""

    def __init__(
        self,
        proximity_bonus_curr_plus_1: float = 6.0,
        proximity_bonus_curr: float = 3.0,
        proximity_bonus_curr_plus_2: float = 2.0,
        anticipation_weight: float = 0.35,
    ) -> None:
        self.bonus_plus_1 = proximity_bonus_curr_plus_1
        self.bonus_curr = proximity_bonus_curr
        self.bonus_plus_2 = proximity_bonus_curr_plus_2
        self.anticipation_weight = anticipation_weight

    def _calc_textual_score(self, transcript_norm: str, slide_norm: str) -> float:
        """Calcula o score textual fuzzy composto."""
        if not transcript_norm or not slide_norm:
            return 0.0

        p_ratio = fuzz.partial_ratio(transcript_norm, slide_norm)
        token_set = fuzz.token_set_ratio(transcript_norm, slide_norm)
        ratio = fuzz.ratio(transcript_norm, slide_norm)

        return (p_ratio * 0.45) + (token_set * 0.35) + (ratio * 0.20)

    def match_slide(
        self,
        transcript: str,
        song: Song,
        current_slide_index: int | None = None,
        anticipation_mode: str = "equilibrado",
        recent_transcript: str = "",
    ) -> SlideMatchResult:
        """Avalia todos os slides da música aplicando contexto, palavras recentes e antecipação."""
        normalized_transcript = normalize_text(transcript)
        normalized_recent = normalize_text(recent_transcript) if recent_transcript else ""
        if not normalized_transcript and not normalized_recent:
            return SlideMatchResult(best_candidate=None, candidates=[])

        search_text = normalized_transcript or normalized_recent
        if not song.slides:
            return SlideMatchResult(best_candidate=None, candidates=[])

        recent_words = set(normalized_recent.split()) if normalized_recent else set()
        candidates: list[SlideCandidate] = []

        for slide in song.slides:
            if not slide.normalized_text:
                slide.normalized_text = normalize_text(slide.text)

            text_score = self._calc_textual_score(search_text, slide.normalized_text)

            # 1. Matching de palavras-chave exclusivas do slide
            if recent_words:
                slide_keywords = [w for w in slide.normalized_text.split() if len(w) > 2 and w not in STOPWORDS]
                if slide_keywords:
                    matched_kws = sum(1 for kw in slide_keywords if kw in recent_words)
                    if matched_kws >= 2 or (len(slide_keywords) <= 3 and matched_kws >= 1):
                        kw_boost = min(95.0, 78.0 + (matched_kws / len(slide_keywords)) * 20.0)
                        text_score = max(text_score, kw_boost)

            # 2. Prioriza as palavras recém-cantadas no último chunk de 1.5s
            if normalized_recent:
                recent_p = fuzz.partial_ratio(normalized_recent, slide.normalized_text)
                recent_tok = fuzz.token_set_ratio(normalized_recent, slide.normalized_text)
                recent_score = max(recent_p, recent_tok)
                if recent_score >= 70.0:
                    text_score = max(text_score, recent_score)

            anticipation_bonus = 0.0
            if anticipation_mode in ("antecipado", "equilibrado") and slide.start_words:
                norm_start = normalize_text(slide.start_words)
                if norm_start:
                    start_ratio = max(
                        fuzz.partial_ratio(search_text, norm_start),
                        fuzz.partial_ratio(normalized_recent, norm_start) if normalized_recent else 0.0,
                    )
                    if start_ratio >= 75:
                        weight = 8.0 if anticipation_mode == "antecipado" else 4.0
                        anticipation_bonus = (start_ratio / 100.0) * weight

            context_bonus = 0.0
            if current_slide_index is not None:
                diff = slide.index - current_slide_index
                if diff == 1:
                    context_bonus = self.bonus_plus_1
                elif diff == 0:
                    context_bonus = self.bonus_curr
                elif diff == 2:
                    context_bonus = self.bonus_plus_2
                elif diff < 0:
                    context_bonus = -2.0

            total_score = min(100.0, text_score + context_bonus + anticipation_bonus)

            candidates.append(
                SlideCandidate(
                    slide_index=slide.index,
                    score=round(total_score, 1),
                    text=slide.text,
                    context_bonus=round(context_bonus + anticipation_bonus, 1),
                )
            )

        candidates.sort(
            key=lambda c: (
                c.score,
                c.context_bonus,
                -abs(c.slide_index - (current_slide_index if current_slide_index is not None else 0)),
            ),
            reverse=True,
        )

        if not candidates:
            return SlideMatchResult(best_candidate=None, candidates=[])

        best = candidates[0]

        return SlideMatchResult(
            best_candidate=best,
            candidates=candidates,
            is_anticipation=best.context_bonus > 0,
        )
