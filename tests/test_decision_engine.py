"""Testes do SlideDecisionEngine e regras anti-falso-positivo."""
import time
from app.decision.slide_decision import SlideDecisionEngine


def test_consecutive_confirmations_required_spec_AC_021():
    """@spec:AC-021 — Exigência de score mínimo e confirmações consecutivas."""
    engine = SlideDecisionEngine(
        threshold_strong=88.0,
        threshold_possible=75.0,
        required_confirmations=2,
        cooldown_seconds=0.5,
    )

    # 1ª detecção: Score forte, mas apenas 1 hit -> Não deve autorizar
    res1 = engine.evaluate(candidate_index=2, candidate_score=90.0, current_slide_index=1)
    assert res1.should_switch is False
    assert res1.consecutive_hits == 1

    # 2ª detecção: Mesmo slide com score forte -> Deve autorizar
    res2 = engine.evaluate(candidate_index=2, candidate_score=89.0, current_slide_index=1)
    assert res2.should_switch is True
    assert res2.target_slide_index == 2
    assert res2.consecutive_hits == 2


def test_cooldown_and_hysteresis_spec_AC_022():
    """@spec:AC-022 — Cooldown pós-troca e histerese contra oscilação rápida."""
    engine = SlideDecisionEngine(
        threshold_strong=88.0,
        threshold_possible=75.0,
        required_confirmations=2,
        cooldown_seconds=0.5,
    )

    # Registra troca para slide 2
    engine.record_switch(slide_index=2)

    # Imediatamente tenta trocar para slide 3 -> Deve bloquear por cooldown
    res = engine.evaluate(candidate_index=3, candidate_score=95.0, current_slide_index=2)
    assert res.should_switch is False
    assert "cooldown" in res.reason.lower()

    # Aguarda expirar cooldown
    time.sleep(0.6)

    # Agora deve aceitar nova detecção normalmente
    res_after = engine.evaluate(candidate_index=3, candidate_score=90.0, current_slide_index=2)
    assert res_after.consecutive_hits == 1


def test_anticipation_modes_spec_AC_023():
    """@spec:AC-023 — Modos de troca configuráveis de antecipação."""
    engine = SlideDecisionEngine(threshold_strong=85.0, required_confirmations=1)
    res = engine.evaluate(candidate_index=3, candidate_score=90.0, current_slide_index=2)
    assert res.should_switch is True


def test_fail_safe_behavior_spec_AC_024():
    """@spec:AC-024 — Comportamento fail-safe de segurança."""
    engine = SlideDecisionEngine(threshold_possible=75.0)

    # Ruído com score muito baixo
    res = engine.evaluate(candidate_index=3, candidate_score=50.0, current_slide_index=2)
    assert res.should_switch is False
    assert res.target_slide_index is None

