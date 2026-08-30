"""Serviço central de automação e orquestração do pipeline Holyrics AutoSlide."""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Literal

import numpy as np

from app.audio.base import AudioSource
from app.audio.capture import DeviceAudioSource
from app.audio.loopback import LoopbackAudioSource
from app.audio.wav_source import WavFileAudioSource
from app.audio.resampler import apply_voice_bandpass_filter
from app.transcription.base import TranscriptionEngine
from app.transcription.groq_whisper import GroqWhisperTranscriber
from app.transcription.faster_whisper import FasterWhisperTranscriber
from app.transcription.buffer import AudioRingBuffer, RollingTranscriptBuffer
from app.transcription.scheduler import ChunkScheduler
from app.transcription.merger import TranscriptMerger
from app.transcription.vad import EnergyVAD
from app.matching.matcher import LyricsMatcher
from app.matching.lyric_tracker import LyricTracker
from app.decision.slide_decision import SlideDecisionEngine
from app.decision.song_decision import SongTransitionDecisionEngine
from app.decision.song_state_machine import SongState
from app.holyrics.service import HolyricsService
from app.models.app_state import AppState
from app.models.song import Song
from app.config.settings import AppSettings
from app.utils.logging import log_event


class AutomationService:
    """Orquestra áudio, transcrição, matching, motor de decisão e integração com o Holyrics."""

    def __init__(
        self,
        settings: AppSettings,
        state: AppState,
        holyrics_service: HolyricsService,
        transcription_engine: TranscriptionEngine | None = None,
    ) -> None:
        self.settings = settings
        self.state = state
        self.holyrics_service = holyrics_service
        if transcription_engine is not None:
            self.transcription_engine = transcription_engine
        elif settings.transcription.groq_api_key:
            self.transcription_engine = GroqWhisperTranscriber(
                api_key=settings.transcription.groq_api_key,
                model=settings.transcription.groq_model,
                base_url=settings.transcription.groq_base_url,
                language=settings.transcription.language,
            )
        else:
            self.transcription_engine = FasterWhisperTranscriber(
                model_size=settings.transcription.model,
                device=settings.transcription.device,
                compute_type=settings.transcription.compute_type,
                language=settings.transcription.language,
            )

        self.audio_ring_buffer = AudioRingBuffer(max_seconds=30.0, sample_rate=16000)
        self.chunk_scheduler = ChunkScheduler(
            self.audio_ring_buffer,
            window_duration=2.5,
            hop_duration=0.8,
            sample_rate=16000,
        )
        self.transcript_merger = TranscriptMerger(max_history_seconds=15.0)
        self.rolling_transcript = RollingTranscriptBuffer(max_duration_seconds=12.0)
        self.vad = EnergyVAD(enabled=settings.transcription.vad_enabled)

        self.matcher = LyricsMatcher(
            song_threshold=settings.decision.song_threshold,
            song_margin=settings.decision.song_margin,
            anticipation_mode=settings.decision.anticipation_mode,
        )
        self.lyric_tracker = LyricTracker()

        self.decision_engine = SlideDecisionEngine(
            threshold_strong=settings.decision.slide_threshold_strong,
            threshold_possible=settings.decision.slide_threshold_possible,
            required_confirmations=settings.decision.consecutive_confirmations,
            cooldown_seconds=settings.decision.cooldown_seconds,
        )

        self.song_decision_engine = SongTransitionDecisionEngine(
            initial_threshold=settings.decision.song_threshold,
            transition_threshold=max(settings.decision.song_threshold + 4.0, 92.0),
            margin=settings.decision.song_margin,
            confirmations=max(settings.decision.consecutive_confirmations + 1, 3),
            transition_min_duration=3.0,
        )

        self._audio_source: AudioSource | None = None
        self._worker_thread: threading.Thread | None = None
        self._is_worker_running = False
        self._manual_pause_until = 0.0

        self.holyrics_service.on_manual_slide_change = self._handle_manual_slide_change
        self.holyrics_service.on_song_change = self._handle_holyrics_song_change

    def reset_context_for_song_change(self) -> None:
        """Limpa completamente todo o histórico de transcrição e decisão ao trocar de música."""
        self.transcript_merger.clear()
        self.rolling_transcript.clear()
        self.decision_engine.reset_candidate()
        self.state.candidate_slide_index = None
        self.state.candidate_score = 0.0
        self.state.candidate_slide_text = ""
        self.state.candidate_hits = 0
        self.state.last_transcript_chunk = ""
        self.state.rolling_transcript = ""

    def _handle_holyrics_song_change(self, new_song: Song, is_manual: bool) -> None:
        """Sincroniza a autoridade da música vinda do Holyrics com a SongStateMachine."""
        if is_manual:
            log_event("HOLYRICS", f"Música sincronizada do Holyrics: '{new_song.title}'.")
            self.reset_context_for_song_change()
            self.song_decision_engine.set_active_song(new_song)
            self.state.current_song = new_song
            self.state.notify()

    def _handle_manual_slide_change(self, new_slide_index: int) -> None:
        """Chamado quando o operador altera o slide manualmente no Holyrics."""
        pause_duration = self.settings.decision.manual_pause_seconds
        self._manual_pause_until = time.time() + pause_duration
        self.state.manual_override_active = True
        self.state.manual_override_remaining = pause_duration
        self.decision_engine.reset_candidate()
        self.state.notify()
        log_event(
            "DECISION",
            f"Automação pausada por {pause_duration}s devido a intervenção manual do operador.",
        )

    def set_mode(self, mode: Literal["PARADO", "MONITOR", "AUTOMATICO"]) -> None:
        """Altera o modo de operação da automação."""
        old_mode = self.state.automation_mode
        self.state.automation_mode = mode
        self.state.notify()
        log_event("APP", f"Modo de operação alterado: {old_mode} -> {mode}")

    def start_audio(self) -> None:
        """Inicia a captura de áudio com base nas configurações ativas."""
        if self.state.audio_capturing:
            return

        last_vu_time = 0.0

        def _levels_cb(rms_db: float, peak_db: float) -> None:
            nonlocal last_vu_time
            now = time.time()
            self.state.audio_rms_db = rms_db
            self.state.audio_peak_db = peak_db
            if now - last_vu_time >= 0.12:
                last_vu_time = now
                self.state.notify()

        def _audio_chunk_cb(chunk: np.ndarray) -> None:
            self.audio_ring_buffer.write(chunk)

        source_type = self.settings.audio.source_type
        if source_type == "wav" and self.settings.audio.wav_file_path:
            self._audio_source = WavFileAudioSource(
                file_path=self.settings.audio.wav_file_path,
                on_levels_update=_levels_cb,
            )
        elif source_type == "loopback":
            self._audio_source = LoopbackAudioSource(
                device_id=self.settings.audio.device_id,
                channel_selection=self.settings.audio.channel_selection,
                on_levels_update=_levels_cb,
            )
        else:
            self._audio_source = DeviceAudioSource(
                device_id=self.settings.audio.device_id,
                channel_selection=self.settings.audio.channel_selection,
                on_levels_update=_levels_cb,
            )

        try:
            self._audio_source.start(_audio_chunk_cb)
            self.state.audio_capturing = True
            self.state.notify()
        except Exception as e:
            log_event("AUDIO", f"Falha ao iniciar captura de áudio: {e}", level=40)
            self.state.audio_capturing = False
            self.state.notify()
            raise

    def stop_audio(self) -> None:
        """Interrompe a captura de áudio."""
        if self._audio_source:
            self._audio_source.stop()
            self._audio_source = None
        self.state.audio_capturing = False
        self.state.audio_rms_db = -60.0
        self.state.audio_peak_db = -60.0
        self.state.notify()

    def _build_context_prompt(self) -> str | None:
        """Gera um prompt dinâmico adaptado ao estado: estrofes locais durante SONG_LOCKED ou neutro durante transições."""
        items: list[str] = []
        is_firmly_locked = (
            self.song_decision_engine.state_machine.state == SongState.SONG_LOCKED
            and self.state.current_song is not None
        )

        if is_firmly_locked and self.state.current_song:
            items.append(self.state.current_song.title)
            slides = self.state.current_song.slides
            curr_idx = self.state.current_slide_index or 0
            start_idx = max(0, curr_idx - 1)
            end_idx = min(len(slides), curr_idx + 3)
            for slide in slides[start_idx:end_idx]:
                if slide.start_words:
                    items.append(slide.start_words)
        elif self.state.playlist.songs:
            # Durante transição ou busca inicial: lista apenas títulos da playlist sem enviesar com estrofes antigas
            for s in self.state.playlist.songs[:4]:
                items.append(s.title)

        if items:
            return ", ".join(items)[:220]
        return None

    def start_worker(self) -> None:
        """Inicia o worker de transcrição e decisão orientado a amostras novas."""
        if self._is_worker_running:
            return
        self._is_worker_running = True

        def _worker_loop() -> None:
            if not self.transcription_engine.is_ready():
                try:
                    self.transcription_engine.load_model()
                    self.state.transcriber_ready = True
                    self.state.notify()
                except Exception as e:
                    log_event("ASR", f"Falha ao carregar modelo Whisper: {e}", level=40)
                    self._is_worker_running = False
                    return

            while self._is_worker_running:
                if self.state.manual_override_active:
                    remaining = self._manual_pause_until - time.time()
                    if remaining > 0:
                        self.state.manual_override_remaining = round(remaining, 1)
                        self.state.notify()
                    else:
                        self.state.manual_override_active = False
                        self.state.manual_override_remaining = 0.0
                        self.state.notify()
                        log_event("DECISION", "Pausa por intervenção manual concluída. Automação retomada.")

                if self.state.automation_mode in ("MONITOR", "AUTOMATICO"):
                    # Scheduler baseado em amostras de áudio novas (Janela 2.5s / Hop 0.8s)
                    if self.chunk_scheduler.has_new_chunk():
                        audio_chunk = self.chunk_scheduler.get_chunk_for_inference()
                        if audio_chunk is not None and len(audio_chunk) > 0 and self.vad.has_speech(audio_chunk):
                            try:
                                context_prompt = self._build_context_prompt()
                                asr_res = self.transcription_engine.transcribe(audio_chunk, prompt=context_prompt)
                                if asr_res.text:
                                    # Deduplica e funde transcrições
                                    self.transcript_merger.add_transcription(asr_res.text, asr_res.timestamp)
                                    self.rolling_transcript.add(asr_res.text, asr_res.timestamp)

                                    slide_text = self.transcript_merger.get_slide_window_text(duration=4.0)
                                    song_text = self.transcript_merger.get_song_window_text(duration=10.0)

                                    self.state.last_transcript_chunk = asr_res.text
                                    self.state.rolling_transcript = song_text
                                    self.state.inference_time_ms = asr_res.inference_time
                                    if asr_res.duration > 0:
                                        self.state.rtf = round((asr_res.inference_time / 1000.0) / asr_res.duration, 2)
                                    self.state.notify()

                                    log_event("ASR", f"Transcrição: \"{asr_res.text}\" ({asr_res.inference_time:.0f}ms)")
                                    self._process_matching_and_decision(
                                        slide_transcript=slide_text,
                                        song_transcript=song_text,
                                        recent_transcript=asr_res.text,
                                    )
                            except Exception as e:
                                log_event("ASR", f"Erro no processamento do chunk: {e}", level=30)

                time.sleep(0.08)

        self._worker_thread = threading.Thread(target=_worker_loop, daemon=True)
        self._worker_thread.start()

    def _process_matching_and_decision(
        self,
        slide_transcript: str,
        song_transcript: str,
        recent_transcript: str = "",
    ) -> None:
        """Compara o texto deduplicado com as músicas e slides aplicando máquina de estados."""
        # Se nenhuma música está travada ou para avaliar transições de música
        if self.state.playlist.songs:
            song_res = self.matcher.match_song(song_transcript, self.state.playlist)
            if song_res.song:
                song_decision = self.song_decision_engine.evaluate(
                    best_song=song_res.song,
                    best_score=song_res.score,
                    second_score=song_res.second_score,
                )
                if song_decision.should_change and song_decision.target_song:
                    is_new_song = self.state.current_song is None or self.state.current_song.id != song_decision.target_song.id
                    if is_new_song:
                        log_event("MATCHER", f"Música travada pelo motor de decisão: '{song_decision.target_song.title}' ({song_decision.reason})")
                        self.reset_context_for_song_change()
                        self.state.current_song = song_decision.target_song
                        self.state.current_slide_index = None
                        self.state.current_slide_number = None
                        self.state.notify()

                        if self.state.automation_mode == "AUTOMATICO" and not self.state.manual_override_active:
                            self.holyrics_service.mark_song_command_sent(song_decision.target_song.id)
                            try:
                                self.holyrics_service.client.show_lyrics_sync(song_decision.target_song.id, initial_index=0)
                            except Exception as e:
                                log_event("HOLYRICS", f"Erro ao enviar ShowLyrics: {e}", level=30)
                        return

        # Avaliação de slides dentro da música travada via LyricTracker e SlideMatcher
        if self.state.current_song and self.state.current_song.slides:
            if self.lyric_tracker.song != self.state.current_song:
                self.lyric_tracker.set_song(self.state.current_song)

            tracker_hyp = self.lyric_tracker.evaluate_evidence(
                transcript_window=slide_transcript,
                current_slide_index=self.state.current_slide_index,
                anticipation_mode=self.settings.decision.anticipation_mode,
            )

            slide_res = self.matcher.match_slide(
                transcript=slide_transcript,
                song=self.state.current_song,
                current_slide_index=self.state.current_slide_index,
                recent_transcript=recent_transcript,
            )

            best_cand = slide_res.best_candidate
            cand_idx = None
            cand_score = 0.0
            cand_text = ""

            if tracker_hyp and (not best_cand or tracker_hyp.final_score >= best_cand.score):
                cand_idx = tracker_hyp.slide_index
                cand_score = tracker_hyp.final_score
                cand_text = self.state.current_song.slides[cand_idx].text if cand_idx < len(self.state.current_song.slides) else ""
            elif best_cand:
                cand_idx = best_cand.slide_index
                cand_score = best_cand.score
                cand_text = best_cand.text

            if cand_idx is not None:
                self.state.candidate_slide_index = cand_idx
                self.state.candidate_slide_text = cand_text
                self.state.candidate_score = cand_score

                dec_res = self.decision_engine.evaluate(
                    candidate_index=cand_idx,
                    candidate_score=cand_score,
                    current_slide_index=self.state.current_slide_index,
                )

                self.state.candidate_hits = dec_res.consecutive_hits
                self.state.required_hits = dec_res.required_hits
                self.state.notify()

                if dec_res.should_switch and dec_res.target_slide_index is not None:
                    if self.state.automation_mode == "AUTOMATICO" and not self.state.manual_override_active:
                        target_idx = dec_res.target_slide_index
                        self.holyrics_service.mark_command_sent(target_idx)
                        try:
                            self.holyrics_service.client.go_to_index_sync(target_idx)
                            self.decision_engine.record_switch(target_idx)
                            self.state.total_slides_switched += 1
                            self.state.current_slide_index = target_idx
                            self.state.current_slide_number = target_idx + 1
                            if target_idx < len(self.state.current_song.slides):
                                self.state.current_slide_text = self.state.current_song.slides[target_idx].text
                            self.state.notify()
                            log_event(
                                "HOLYRICS",
                                f"Comando de slide enviado com sucesso: {target_idx + 1}/{len(self.state.current_song.slides)}",
                            )
                        except Exception as e:
                            log_event("HOLYRICS", f"Falha ao enviar troca de slide: {e}", level=40)
                    elif self.state.automation_mode == "MONITOR":
                        log_event(
                            "DECISION",
                            f"[MODO MONITOR] Trocaria para o slide {dec_res.target_slide_index + 1} (Score: {best_cand.score:.1f}%)",
                        )

    def stop_worker(self) -> None:
        """Interrompe o worker de transcrição."""
        self._is_worker_running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
        self._worker_thread = None

