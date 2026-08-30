"""Testes para o LyricTracker V2 com grafo de transições e assinaturas de início de frase."""
from app.matching.lyric_tracker import LyricTracker
from app.models.song import Song
from app.models.slide import SongSlide


def _create_sample_song() -> Song:
    slides = [
        SongSlide(index=0, text="Aquele que acalma o vento e o mar", start_words="Aquele que acalma"),
        SongSlide(index=1, text="Santo e Poderoso é o Teu nome", start_words="Santo e Poderoso"),
        SongSlide(index=2, text="Aleluia ao Deus da minha salvação", start_words="Aleluia ao Deus"),  # Refrão 1
        SongSlide(index=3, text="Toda a Terra se prostra diante de Ti", start_words="Toda a Terra"),
        SongSlide(index=4, text="Teu reino nunca terá fim", start_words="Teu reino nunca"),
        SongSlide(index=5, text="Aleluia ao Deus da minha salvação", start_words="Aleluia ao Deus"),  # Refrão 2
    ]
    return Song(id="101", title="Santo e Poderoso", artist="Worship", slides=slides)


def test_early_phrase_start_detection():
    """Valida detecção antecipada na primeira frase cantada do slide seguinte."""
    song = _create_sample_song()
    tracker = LyricTracker(song)

    # Cantor está no slide 0 e começa a cantar as 2 primeiras palavras do slide 1: 'Santo e poderoso'
    hyp = tracker.evaluate_evidence("santo e poderoso", current_slide_index=0)
    assert hyp is not None
    assert hyp.slide_index == 1
    assert hyp.is_early_start
    assert hyp.final_score >= 90.0


def test_natural_transition_prior():
    """Valida que o próximo slide ganha prioridade natural sobre saltos aleatórios com similaridade aproximada."""
    song = _create_sample_song()
    tracker = LyricTracker(song)

    # Texto com correspondência moderada com slide 1
    hyp = tracker.evaluate_evidence("o Teu nome e poder", current_slide_index=0)
    assert hyp is not None
    assert hyp.slide_index == 1
    assert hyp.transition_prior > 0


def test_repeated_chorus_disambiguation_by_graph():
    """Valida que ocorrências repetidas de refrão são desambiguadas pela posição atual no grafo."""
    song = _create_sample_song()
    tracker = LyricTracker(song)

    # Se estamos no slide 4 ("Teu reino...") e o cantor canta o refrão ("Aleluia ao Deus...")
    # O rastreador deve selecionar a ocorrência 5 (imediatamente seguinte), não a ocorrência 2 (lá atrás).
    hyp = tracker.evaluate_evidence("Aleluia ao Deus da minha salvacao", current_slide_index=4)
    assert hyp is not None
    assert hyp.slide_index == 5
