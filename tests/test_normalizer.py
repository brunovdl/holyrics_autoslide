"""Testes do módulo de normalização de texto e fala."""
from app.matching.normalizer import normalize_text, remove_accents


def test_remove_accents():
    assert remove_accents("Não TEMAS, Sou contigo!") == "Nao TEMAS, Sou contigo!"
    assert remove_accents("Jesus é o caminho, a verdade e a vida") == "Jesus e o caminho, a verdade e a vida"


def test_normalize_text_full_spec_AC_017():
    """@spec:AC-017 — Normalização textual e de fala para matching."""
    raw_text = "Porque eu NÃO estou sozinho! Nesta guerra está comigo, o braço forte."
    normalized = normalize_text(raw_text)
    assert "porque eu nao estou sozinho" in normalized
    assert "nesta guerra esta comigo" in normalized
    assert "o braco forte" in normalized

    # Testa contrações de fala comuns
    speech_text = "To aqui pra te adorar, ne?"
    norm_speech = normalize_text(speech_text)
    assert norm_speech == "estou aqui para te adorar nao e"

