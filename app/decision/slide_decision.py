"""Motor de decisão e proteção anti-falso-positivo para troca de slides."""
from __future__ import annotations

import time
from dataclasses import dataclass
from app.utils.logging import log_event


@dataclass
class DecisionResult:
    """Resultado da avaliação do motor de decisão."""
    should_switch: bool
    target_slide_index: int | None
    confidence: float
    consecutive_hits: int
    required_hits: int
    reason: str


class SlideDecisionEngine:
    """Valida evidências, histerese, cooldown e confirmações antes de autorizar troca."""

    def __init__(
        self,
        threshold_strong: float = 88.0,
        threshold_possible: float = 75.0,
        required_confirmations: int = 2,
        cooldown_seconds: float = 0.8,
    ) -> None:
        self.threshold_strong = threshold_strong
        self.threshold_possible = threshold_possible
        self.required_confirmations = required_confirmations
        self.cooldown_seconds = cooldown_seconds

        self._candidate_slide: int | None = None
        self._candidate_hits = 0
        self._last_switch_time = 0.0
        self._last_switched_slide: int | None = None
        self._previous_slide: int | None = None

    def reset_candidate(self) -> None:
        """Reinicia o contador de candidatos."""
        self._candidate_slide = None
        self._candidate_hits = 0

    def record_switch(self, slide_index: int) -> None:
        """Registra que uma troca foi realizada com sucesso."""
        self._previous_slide = self._last_switched_slide
        self._last_switch_time = time.time()
        self._last_switched_slide = slide_index
        self.reset_candidate()

    def evaluate(
        self,
        candidate_index: int | None,
        candidate_score: float,
        current_slide_index: int | None,
    ) -> DecisionResult:
        """Avalia se as evidências acumuladas justificam a troca de slide."""
        now = time.time()

        if candidate_index is None or candidate_score < self.threshold_possible:
            self.reset_candidate()
            return DecisionResult(
                should_switch=False,
                target_slide_index=None,
                confidence=candidate_score,
                consecutive_hits=0,
                required_hits=self.required_confirmations,
                reason="Score abaixo do threshold mínimo (evidência fraca/ruído)",
            )

        if current_slide_index is not None and candidate_index == current_slide_index:
            self.reset_candidate()
            return DecisionResult(
                should_switch=False,
                target_slide_index=candidate_index,
                confidence=candidate_score,
                consecutive_hits=0,
                required_hits=self.required_confirmations,
                reason="Candidato é o slide atualmente em exibição",
            )

        time_since_switch = now - self._last_switch_time
        if time_since_switch < self.cooldown_seconds:
            return DecisionResult(
                should_switch=False,
                target_slide_index=candidate_index,
                confidence=candidate_score,
                consecutive_hits=self._candidate_hits,
                required_hits=self.required_confirmations,
                reason=f"Em período de cooldown ({time_since_switch:.2f}s < {self.cooldown_seconds:.2f}s)",
            )

        # Proteção contra flapping: voltar imediatamente ao slide anterior sem score excepcional
        if (
            self._previous_slide is not None
            and candidate_index == self._previous_slide
            and time_since_switch < (self.cooldown_seconds * 2.0)
            and candidate_score < (self.threshold_strong + 5.0)
        ):
            return DecisionResult(
                should_switch=False,
                target_slide_index=candidate_index,
                confidence=candidate_score,
                consecutive_hits=self._candidate_hits,
                required_hits=self.required_confirmations,
                reason="Bloqueio por histerese contra oscilações rápidas (flapping)",
            )

        if self._candidate_slide == candidate_index:
            self._candidate_hits += 1
        else:
            self._candidate_slide = candidate_index
            self._candidate_hits = 1

        is_strong = candidate_score >= self.threshold_strong
        is_possible = candidate_score >= self.threshold_possible

        has_enough_hits = (
            (is_strong and self._candidate_hits >= self.required_confirmations)
            or (is_possible and self._candidate_hits >= max(2, self.required_confirmations + 1))
            or candidate_score >= 96.0
        )

        if has_enough_hits:
            log_event(
                "DECISION",
                f"Troca autorizada para o slide {candidate_index + 1} (Score: {candidate_score:.1f}%, Confirmações: {self._candidate_hits})",
            )
            return DecisionResult(
                should_switch=True,
                target_slide_index=candidate_index,
                confidence=candidate_score,
                consecutive_hits=self._candidate_hits,
                required_hits=self.required_confirmations,
                reason="Confirmações e score atingidos com sucesso",
            )

        return DecisionResult(
            should_switch=False,
            target_slide_index=candidate_index,
            confidence=candidate_score,
            consecutive_hits=self._candidate_hits,
            required_hits=self.required_confirmations,
            reason=f"Aguardando confirmações consecutivas ({self._candidate_hits}/{self.required_confirmations})",
        )
