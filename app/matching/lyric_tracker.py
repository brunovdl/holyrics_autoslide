"""Rastreador probabilístico de letra com grafo de transições e assinaturas de início de estrofe."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional
from rapidfuzz import fuzz

from app.models.song import Song
from app.models.slide import SongSlide
from app.matching.normalizer import normalize_text


@dataclass
class SlideSignature:
    """Assinatura pré-computada de um slide para reconhecimento de ultra-baixa latência."""
    slide_index: int
    raw_text: str
    normalized_text: str
    start_2_words: str
    start_3_words: str
    start_4_words: str
    words: Set[str]
    is_chorus_candidate: bool = False


@dataclass
class LyricTrackHypothesis:
    """Hipótese de localização dentro da letra da música."""
    slide_index: int
    emission_score: float
    transition_prior: float
    start_word_bonus: float
    raw_score: float
    final_score: float
    is_early_start: bool
    reason: str


@dataclass
class LyricTrackResult:
    """Resultado consolidado de rastreamento com melhor hipótese e margem de confiança."""
    best_hypothesis: Optional[LyricTrackHypothesis]
    second_score: float = 0.0
    margin: float = 0.0
    is_fast_path: bool = False


class LyricTracker:
    """Rastreador de letra baseado no universo fechado de slides e grafo de transições."""

    def __init__(self, song: Optional[Song] = None) -> None:
        self.song: Optional[Song] = None
        self.signatures: List[SlideSignature] = []
        self._chorus_indices: Set[int] = set()
        if song:
            self.set_song(song)

    def set_song(self, song: Song) -> None:
        """Inicializa o rastreador e pré-computa assinaturas estruturais dos slides."""
        self.song = song
        self.signatures = []
        self._chorus_indices = set()

        text_counts: Dict[str, List[int]] = {}
        for s in song.slides:
            norm = normalize_text(s.text)
            tokens = norm.split()
            s2 = " ".join(tokens[:2]) if len(tokens) >= 2 else norm
            s3 = " ".join(tokens[:3]) if len(tokens) >= 3 else norm
            s4 = " ".join(tokens[:4]) if len(tokens) >= 4 else norm
            words = set(w for w in tokens if len(w) > 2)

            sig = SlideSignature(
                slide_index=s.index,
                raw_text=s.text,
                normalized_text=norm,
                start_2_words=s2,
                start_3_words=s3,
                start_4_words=s4,
                words=words,
            )
            self.signatures.append(sig)
            text_counts.setdefault(norm, []).append(s.index)

        # Identifica refrões repetidos estruturalmente
        for norm, indices in text_counts.items():
            if len(indices) > 1:
                for idx in indices:
                    self._chorus_indices.add(idx)
                    if idx < len(self.signatures):
                        self.signatures[idx].is_chorus_candidate = True

    def evaluate_fast_path(
        self,
        recent_chunk: str,
        current_slide_index: Optional[int],
    ) -> Optional[LyricTrackHypothesis]:
        """FAST PATH: Avalia apenas a transição natural N -> N+1 no áudio instantâneo do último chunk."""
        if current_slide_index is None or not self.signatures:
            return None

        next_idx = current_slide_index + 1
        if next_idx >= len(self.signatures):
            return None

        norm_chunk = normalize_text(recent_chunk)
        if not norm_chunk:
            return None

        sig = self.signatures[next_idx]

        # Verifica se o início do próximo slide está presente no chunk instantâneo
        has_start_3 = len(sig.start_3_words) > 3 and sig.start_3_words in norm_chunk
        has_start_2 = len(sig.start_2_words) > 4 and sig.start_2_words in norm_chunk

        if has_start_3 or has_start_2:
            return LyricTrackHypothesis(
                slide_index=next_idx,
                emission_score=95.0,
                transition_prior=15.0,
                start_word_bonus=15.0,
                raw_score=125.0,
                final_score=98.0,
                is_early_start=True,
                reason="fast_path_proximo_slide",
            )
        return None

    def evaluate_evidence(
        self,
        transcript_window: str,
        current_slide_index: Optional[int] = None,
        anticipation_mode: str = "equilibrado",
    ) -> LyricTrackResult:
        """Avalia a evidência de áudio recente contra o grafo de transição dos slides."""
        norm_input = normalize_text(transcript_window)
        if not norm_input or not self.signatures:
            return LyricTrackResult(best_hypothesis=None)

        input_words = set(norm_input.split())
        curr_idx = current_slide_index if current_slide_index is not None else 0
        num_slides = len(self.signatures)

        hypotheses: List[LyricTrackHypothesis] = []

        for sig in self.signatures:
            idx = sig.slide_index

            # 1. Score de Emissão Acústica / Textual
            p_ratio = fuzz.partial_ratio(norm_input, sig.normalized_text)
            token_set = fuzz.token_set_ratio(norm_input, sig.normalized_text)
            emission = (p_ratio * 0.50) + (token_set * 0.50)

            # 2. Detecção de Início Imediato de Estrofe (Primeiras 2-3 palavras)
            is_early_start = False
            start_bonus = 0.0

            if len(sig.start_3_words) > 3 and sig.start_3_words in norm_input:
                start_bonus = 15.0
                is_early_start = True
            elif len(sig.start_2_words) > 3 and sig.start_2_words in norm_input:
                start_bonus = 10.0
                is_early_start = True

            # 3. Grafo Probabilístico de Transição
            transition_prior = 0.0
            jump_penalty = 0.0

            if current_slide_index is not None:
                if idx == curr_idx + 1:
                    # Transição natural N -> N+1
                    transition_prior = 15.0
                elif idx == curr_idx:
                    # Continuação no slide atual
                    transition_prior = 4.0
                elif idx == curr_idx + 2:
                    # Salto curto N -> N+2
                    transition_prior = 3.0
                elif idx in self._chorus_indices and idx != curr_idx:
                    # Retorno para refrão
                    transition_prior = 2.0
                else:
                    # Salto distante ou salto para trás
                    dist = abs(idx - curr_idx)
                    jump_penalty = min(20.0, dist * 3.0)

            # 4. Ajuste por modo de antecipação
            if anticipation_mode in ("antecipado", "rapido") and is_early_start and idx == curr_idx + 1:
                start_bonus += 5.0

            raw_score = emission + transition_prior + start_bonus - jump_penalty
            final = min(100.0, max(0.0, raw_score))

            reason = "matching_padrao"
            if is_early_start:
                reason = "inicio_de_frase"
            elif idx == curr_idx + 1:
                reason = "sequencia_natural"
            elif idx in self._chorus_indices:
                reason = "retorno_refrao"

            hypotheses.append(
                LyricTrackHypothesis(
                    slide_index=idx,
                    emission_score=round(emission, 1),
                    transition_prior=round(transition_prior, 1),
                    start_word_bonus=round(start_bonus, 1),
                    raw_score=round(raw_score, 1),
                    final_score=round(final, 1),
                    is_early_start=is_early_start,
                    reason=reason,
                )
            )

        # Ordena pelo raw_score para que priors e bônus desfaçam empates de 100%
        hypotheses.sort(key=lambda h: (h.raw_score, -abs(h.slide_index - curr_idx)), reverse=True)
        if not hypotheses:
            return LyricTrackResult(best_hypothesis=None)

        best = hypotheses[0]
        second_score = hypotheses[1].final_score if len(hypotheses) > 1 else 0.0
        margin = max(0.0, round(best.final_score - second_score, 1))

        return LyricTrackResult(
            best_hypothesis=best,
            second_score=second_score,
            margin=margin,
            is_fast_path=False,
        )
