"""Testes do LyricsMatcher para identificação de músicas e slides."""
from app.matching.slide_matcher import SlideMatcher
from app.matching.song_matcher import SongMatcher
from app.models.slide import SongSlide
from app.models.song import PlaylistSnapshot, Song


def create_sample_playlist() -> PlaylistSnapshot:
    song1 = Song(
        id="1",
        title="Escape",
        artist="Renascer Praise",
        slides=[
            SongSlide(index=0, text="Aquele que acalma o vento", start_words="Aquele que acalma"),
            SongSlide(index=1, text="Aquele que aquieta o mar", start_words="Aquele que aquieta"),
            SongSlide(index=2, text="É o mesmo que me faz vencer", start_words="É o mesmo que"),
            SongSlide(index=3, text="E nunca me deixará", start_words="E nunca me"),
            SongSlide(index=4, text="O meu Deus é o Deus de escape", start_words="O meu Deus é"),  # Refrão 1
            SongSlide(index=5, text="Ele abre o mar pra eu passar", start_words="Ele abre o"),
            SongSlide(index=6, text="O meu Deus é o Deus de escape", start_words="O meu Deus é"),  # Refrão 2
            SongSlide(index=7, text="E me faz triunfar", start_words="E me faz"),
        ],
        full_text="Aquele que acalma o vento Aquele que aquieta o mar É o mesmo que me faz vencer E nunca me deixará O meu Deus é o Deus de escape Ele abre o mar pra eu passar O meu Deus é o Deus de escape E me faz triunfar",
    )

    song2 = Song(
        id="2",
        title="Bondade de Deus",
        artist="Isaías Saad",
        slides=[
            SongSlide(index=0, text="Te amo Deus, tua graça nunca falha", start_words="Te amo Deus"),
            SongSlide(index=1, text="Todos os meus dias em tuas mãos estão", start_words="Todos os meus"),
        ],
        full_text="Te amo Deus tua graça nunca falha Todos os meus dias em tuas mãos estão",
    )

    return PlaylistSnapshot(songs=[song1, song2])


def test_identify_song_spec_AC_018():
    """@spec:AC-018 — Identificação automática da música na playlist."""
    playlist = create_sample_playlist()
    song_matcher = SongMatcher(threshold=75.0, min_margin=5.0)

    # Transcrição correspondente à música 1
    transcript = "aquele que acalma o vento e aquieta o mar"
    res = song_matcher.identify_song(transcript, playlist)

    assert res.is_confident is True
    assert res.song is not None
    assert res.song.id == "1"
    assert res.song.title == "Escape"
    assert res.margin >= 5.0


def test_match_slide_contextual_spec_AC_019():
    """@spec:AC-019 — Identificação do slide com busca contextual e bônus de proximidade."""
    playlist = create_sample_playlist()
    song = playlist.songs[0]
    slide_matcher = SlideMatcher()

    # Quando estamos no slide 0 e a transcrição é do slide 1
    transcript = "aquele que aquieta o mar e nunca me deixará"
    res = slide_matcher.match_slide(
        transcript=transcript,
        song=song,
        current_slide_index=0,
        anticipation_mode="equilibrado",
    )

    assert res.best_candidate is not None
    assert res.best_candidate.slide_index == 1
    assert res.best_candidate.score >= 80.0


def test_match_repeated_chorus_spec_AC_020():
    """@spec:AC-020 — Resolução de refrões e trechos repetidos."""
    playlist = create_sample_playlist()
    song = playlist.songs[0]
    slide_matcher = SlideMatcher()

    # Slide 4 e Slide 6 têm texto similar ("O meu Deus é o Deus de escape")
    # Estando no slide 5, deve preferir o slide 6 (sequência natural)
    transcript = "o meu Deus é o Deus de escape"
    res = slide_matcher.match_slide(
        transcript=transcript,
        song=song,
        current_slide_index=5,
        anticipation_mode="equilibrado",
    )

    assert res.best_candidate is not None
    assert res.best_candidate.slide_index == 6

