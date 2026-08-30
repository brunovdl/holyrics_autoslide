"""Motor de decisão e confirmação de transições de músicas da playlist."""
from __future__ import annotations

import dataclasses
import time
from app.decision.song_state_machine import SongState, SongStateMachine
from app.models.song import Song


@dataclasses.dataclass
class SongDecisionResult:
    """Resultado da avaliação de transição de música."""
    should_change: bool
    target_song: Song | None = None
    reason: str = ""
    current_state: SongState = SongState.SEARCHING_SONG


class SongTransitionDecisionEngine:
    """Valida evidências acústicas para travar ou realizar a transição de música de forma estrita."""

    def __init__(
        self,
        initial_threshold: float = 90.0,
        transition_threshold: float = 92.0,
        margin: float = 10.0,
        confirmations: int = 3,
        transition_min_duration: float = 3.0,
    ) -> None:
        self.initial_threshold = initial_threshold
        self.transition_threshold = transition_threshold
        self.margin = margin
        self.confirmations = confirmations
        self.transition_min_duration = transition_min_duration
        self.state_machine = SongStateMachine()

    def reset(self) -> None:
        """Limpa o estado de decisão de música."""
        self.state_machine.clear()

    def set_active_song(self, song: Song) -> None:
        """Fixa diretamente a música ativa."""
        self.state_machine.set_locked_song(song)

    def evaluate(
        self,
        best_song: Song | None,
        best_score: float,
        second_score: float = 0.0,
        now: float | None = None,
    ) -> SongDecisionResult:
        """Avalia se uma nova música deve ser travada ou se a música atual permanece."""
        current_time = now if now is not None else time.time()
        curr_state = self.state_machine.state
        locked_song = self.state_machine.locked_song

        if best_song is None or best_score <= 0.0:
            return SongDecisionResult(should_change=False, current_state=curr_state)

        # Estado 1: SEARCHING_SONG (nenhuma música travada)
        if curr_state == SongState.SEARCHING_SONG:
            if best_score >= self.initial_threshold:
                self.state_machine.state = SongState.SONG_CANDIDATE
                self.state_machine.candidate_song = best_song
                self.state_machine.candidate_hits = 1
                self.state_machine.candidate_started_at = current_time

                if self.confirmations <= 1:
                    self.state_machine.set_locked_song(best_song)
                    return SongDecisionResult(
                        should_change=True,
                        target_song=best_song,
                        reason=f"Música inicial identificada com score {best_score:.1f}%",
                        current_state=SongState.SONG_LOCKED,
                    )
            return SongDecisionResult(should_change=False, current_state=self.state_machine.state)

        # Estado 2: SONG_CANDIDATE (aguardando confirmações da primeira música)
        if curr_state == SongState.SONG_CANDIDATE:
            if self.state_machine.candidate_song and self.state_machine.candidate_song.id == best_song.id:
                if best_score >= self.initial_threshold:
                    self.state_machine.candidate_hits += 1
                    if self.state_machine.candidate_hits >= self.confirmations:
                        self.state_machine.set_locked_song(best_song)
                        return SongDecisionResult(
                            should_change=True,
                            target_song=best_song,
                            reason=f"Música confirmada com {self.state_machine.candidate_hits} hits (score {best_score:.1f}%)",
                            current_state=SongState.SONG_LOCKED,
                        )
                else:
                    self.state_machine.candidate_hits = max(0, self.state_machine.candidate_hits - 1)
            else:
                self.state_machine.candidate_song = best_song
                self.state_machine.candidate_hits = 1 if best_score >= self.initial_threshold else 0
                self.state_machine.candidate_started_at = current_time
            return SongDecisionResult(should_change=False, current_state=self.state_machine.state)

        # Estado 3 & 4: SONG_LOCKED ou SONG_TRANSITION_CANDIDATE
        if locked_song and best_song.id == locked_song.id:
            if curr_state == SongState.SONG_TRANSITION_CANDIDATE:
                self.state_machine.state = SongState.SONG_LOCKED
                self.state_machine.candidate_song = None
                self.state_machine.candidate_hits = 0
            return SongDecisionResult(should_change=False, current_state=SongState.SONG_LOCKED)

        # Candidato diferente da música travada: exige threshold estrito e margem
        score_diff = best_score - second_score
        has_required_margin = score_diff >= self.margin

        if best_score >= self.transition_threshold and has_required_margin:
            if curr_state == SongState.SONG_LOCKED:
                self.state_machine.state = SongState.SONG_TRANSITION_CANDIDATE
                self.state_machine.candidate_song = best_song
                self.state_machine.candidate_hits = 1
                self.state_machine.candidate_started_at = current_time
            elif curr_state == SongState.SONG_TRANSITION_CANDIDATE:
                if self.state_machine.candidate_song and self.state_machine.candidate_song.id == best_song.id:
                    self.state_machine.candidate_hits += 1
                    elapsed = current_time - self.state_machine.candidate_started_at

                    if self.state_machine.candidate_hits >= self.confirmations and elapsed >= self.transition_min_duration:
                        self.state_machine.set_locked_song(best_song)
                        return SongDecisionResult(
                            should_change=True,
                            target_song=best_song,
                            reason=f"Transição autorizada: {best_song.title} ({best_score:.1f}% com margem {score_diff:.1f}% após {elapsed:.1f}s)",
                            current_state=SongState.SONG_LOCKED,
                        )
                else:
                    self.state_machine.candidate_song = best_song
                    self.state_machine.candidate_hits = 1
                    self.state_machine.candidate_started_at = current_time
        else:
            if curr_state == SongState.SONG_TRANSITION_CANDIDATE:
                self.state_machine.candidate_hits = max(0, self.state_machine.candidate_hits - 1)
                if self.state_machine.candidate_hits == 0:
                    self.state_machine.state = SongState.SONG_LOCKED
                    self.state_machine.candidate_song = None

        return SongDecisionResult(should_change=False, current_state=self.state_machine.state)
