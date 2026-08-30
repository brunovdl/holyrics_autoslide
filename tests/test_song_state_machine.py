"""Testes para a máquina de estados e motor de transição de músicas."""
from app.decision.song_decision import SongTransitionDecisionEngine
from app.decision.song_state_machine import SongState
from app.models.song import Song


def test_song_locking_and_noise_rejection():
    """Valida que chunks ruidosos isolados não trocam a música travada."""
    engine = SongTransitionDecisionEngine(
        initial_threshold=90.0,
        transition_threshold=92.0,
        margin=10.0,
        confirmations=3,
        transition_min_duration=3.0,
    )

    song_a = Song(id="1", title="Escape", artist="", slides=[])
    song_b = Song(id="2", title="Emaus", artist="", slides=[])

    # Trava a música A
    engine.set_active_song(song_a)
    assert engine.state_machine.state == SongState.SONG_LOCKED
    assert engine.state_machine.locked_song == song_a

    # 1 chunk ruidoso aponta música B com 91% (abaixo do threshold de transição de 92%)
    res1 = engine.evaluate(best_song=song_b, best_score=91.0, second_score=70.0, now=10.0)
    assert not res1.should_change
    assert engine.state_machine.state == SongState.SONG_LOCKED

    # 1 chunk apontando música B com 94% inicia candidatura mas NÃO troca
    res2 = engine.evaluate(best_song=song_b, best_score=94.0, second_score=75.0, now=11.0)
    assert not res2.should_change
    assert engine.state_machine.state == SongState.SONG_TRANSITION_CANDIDATE
    assert engine.state_machine.candidate_hits == 1

    # 2º chunk consecutivo de música B
    res3 = engine.evaluate(best_song=song_b, best_score=94.0, second_score=75.0, now=12.0)
    assert not res3.should_change
    assert engine.state_machine.candidate_hits == 2

    # 3º chunk consecutivo de música B após 3.0s -> autoriza a transição!
    res4 = engine.evaluate(best_song=song_b, best_score=95.0, second_score=75.0, now=14.5)
    assert res4.should_change
    assert res4.target_song == song_b
    assert engine.state_machine.state == SongState.SONG_LOCKED
