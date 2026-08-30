"""Identificação contextual de slides com resolução de refrões e antecipação."""
from __future__ import annotations

from dataclasses import dataclass
from rapidfuzz import fuzz

from app.models.song import Song
from app.models.slide import SlideCandidate
from app.matching.normalizer import normalize_text


# Stopwords refinadas para letras de música (preserva 'nao' e termos semânticos de louvor)
STOPWORDS = {
    "e", "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "por", "pelo", "pela", "pelos", "pelas", "com", "sem",
    "para", "pra", "pro", "pras", "pros", "que", "se", "eu", "tu", "ele", "ela", "nos", "vos",
    "eles", "elas", "me", "te", "lhe", "lhes", "meu", "minha", "teu", "tua", "seu", "sua",
    "nosso", "nossa", "isso", "isto", "aquilo", "este", "esta", "esse", "essa", "aquele",
    "aquela", "ja", "mais", "mas", "bem", "como", "quando", "onde", "quem", "sim", "vai"
}


@dataclass
class SlideMatchResult:
    """Resultado da avaliação de slides."""
    best_candidate: SlideCandidate | None
    candidates: list[SlideCandidate]
    is_anticipation: bool = False
    is_local_match: bool = True


class SlideMatcher:
    """Calcula similaridade textual com busca local prioritária e bônus contextuais."""

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
        """Calcula o score textual fuzzy balanceado."""
        if not transcript_norm or not slide_norm:
            return 0.0

        p_ratio = fuzz.partial_ratio(transcript_norm, slide_norm)
        token_set = fuzz.token_set_ratio(transcript_norm, slide_norm)
        ratio = fuzz.ratio(transcript_norm, slide_norm)

        # Combina partial_ratio, token_set_ratio e ratio sem deixar token_set dominar isoladamente
        return (p_ratio * 0.45) + (token_set * 0.35) + (ratio * 0.20)

    def _score_slide(
        self,
        slide,
        search_text: str,
        normalized_recent: str,
        recent_words: set[str],
        current_slide_index: int | None,
        anticipation_mode: str,
    ) -> SlideCandidate:
        if not slide.normalized_text:
            slide.normalized_text = normalize_text(slide.text)

        text_score = self._calc_textual_score(search_text, slide.normalized_text)

        # Matching de palavras-chave exclusivas (exige pelo menos 2 palavras significativas)
        if recent_words:
            slide_keywords = [w for w in slide.normalized_text.split() if len(w) > 2 and w not in STOPWORDS]
            if len(slide_keywords) >= 2:
                matched_kws = sum(1 for kw in slide_keywords if kw in recent_words)
                if matched_kws >= 2:
                    kw_boost = min(92.0, 75.0 + (matched_kws / len(slide_keywords)) * 20.0)
                    text_score = max(text_score, kw_boost)

        if normalized_recent:
            recent_p = fuzz.partial_ratio(normalized_recent, slide.normalized_text)
            recent_tok = fuzz.token_set_ratio(normalized_recent, slide.normalized_text)
            recent_score = (recent_p * 0.6) + (recent_tok * 0.4)
            if recent_score >= 72.0:
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
                context_bonus = -3.0
            elif diff > 2:
                context_bonus = -4.0

        total_score = min(100.0, max(0.0, text_score + context_bonus + anticipation_bonus))

        return SlideCandidate(
            slide_index=slide.index,
            score=round(total_score, 1),
            text=slide.text,
            context_bonus=round(context_bonus + anticipation_bonus, 1),
        )

    def match_slide(
        self,
        transcript: str,
        song: Song,
        current_slide_index: int | None = None,
        anticipation_mode: str = "equilibrado",
        recent_transcript: str = "",
    ) -> SlideMatchResult:
        """Avalia todos os slides comparando a hipótese local e global sem bloqueios prematuros."""
        normalized_transcript = normalize_text(transcript)
        normalized_recent = normalize_text(recent_transcript) if recent_transcript else ""
        if not normalized_transcript and not normalized_recent:
            return SlideMatchResult(best_candidate=None, candidates=[])

        search_text = normalized_transcript or normalized_recent
        if not song.slides:
            return SlideMatchResult(best_candidate=None, candidates=[])

        recent_words = set(normalized_recent.split()) if normalized_recent else set()

        all_candidates: list[SlideCandidate] = [
            self._score_slide(
                slide=s,
                search_text=search_text,
                normalized_recent=normalized_recent,
                recent_words=recent_words,
                current_slide_index=current_slide_index,
                anticipation_mode=anticipation_mode,
            )
            for s in song.slides
        ]

        all_candidates.sort(
            key=lambda c: (c.score, c.context_bonus),
            reverse=True,
        )

        if not all_candidates:
            return SlideMatchResult(best_candidate=None, candidates=[])

        if current_slide_index is not None and len(song.slides) > 1:
            local_indices = {
                current_slide_index - 1,
                current_slide_index,
                current_slide_index + 1,
                current_slide_index + 2,
            }
            local_candidates = [c for c in all_candidates if c.slide_index in local_indices]
            global_candidates = [c for c in all_candidates if c.slide_index not in local_indices]

            best_local = local_candidates[0] if local_candidates else None
            best_global = global_candidates[0] if global_candidates else None

            # Regra de decisão balanceada local vs global:
            # Um slide global (ex: retorno ao refrão com 95%) só vence o vizinho local se tiver evidência esmagadora (+10%)
            if best_global and (
                not best_local
                or best_local.score < 72.0
                or (best_global.score >= 90.0 and best_global.score >= best_local.score + 10.0)
            ):
                chosen = best_global
                is_local = False
            elif best_local:
                chosen = best_local
                is_local = True
            else:
                chosen = all_candidates[0]
                is_local = False
        else:
            chosen = all_candidates[0]
            is_local = True

        return SlideMatchResult(
            best_candidate=chosen,
            candidates=all_candidates,
            is_anticipation=chosen.context_bonus > 0,
            is_local_match=is_local,
        )
