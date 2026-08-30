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
from app.transcription.vad import EnergyVAD
from app.matching.matcher import LyricsMatcher
from app.decision.slide_decision import SlideDecisionEngine
from app.holyrics.service import HolyricsService
from app.models.app_state import AppState
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
        self.rolling_transcript = RollingTranscriptBuffer(max_duration_seconds=12.0)
        self.vad = EnergyVAD(enabled=settings.transcription.vad_enabled)

        self.matcher = LyricsMatcher(
            song_threshold=settings.decision.song_threshold,
            song_margin=settings.decision.song_margin,
            anticipation_mode=settings.decision.anticipation_mode,
        )

        self.decision_engine = SlideDecisionEngine(
            threshold_strong=settings.decision.slide_threshold_strong,
            threshold_possible=settings.decision.slide_threshold_possible,
            required_confirmations=settings.decision.consecutive_confirmations,
            cooldown_seconds=settings.decision.cooldown_seconds,
        )

        self._audio_source: AudioSource | None = None
        self._worker_thread: threading.Thread | None = None
        self._is_worker_running = False
        self._manual_pause_until = 0.0

        self.holyrics_service.on_manual_slide_change = self._handle_manual_slide_change

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
            if now - last_vu_time >= 0.12:  # Throttling inteligente ~8 FPS
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
                on_levels_update=_levels_cb,
            )
        else:
            self._audio_source = DeviceAudioSource(
                device_id=self.settings.audio.device_id,
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
        """Gera um vocabulário dinâmico com base na música atual e playlist para guiar o Whisper."""
        items: list[str] = []
        if self.state.current_song:
            items.append(self.state.current_song.title)
            for slide in self.state.current_song.slides[:4]:
                if slide.start_words:
                    items.append(slide.start_words)
        elif self.state.playlist.songs:
            for s in self.state.playlist.songs[:3]:
                items.append(s.title)

        if items:
            return ", ".join(items)[:200]
        return None

    def start_worker(self) -> None:
        """Inicia o worker de transcrição e decisão em thread assíncrona."""
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

            chunk_duration = self.settings.audio.chunk_duration
            step_interval = 0.18

            while self._is_worker_running:
                loop_start = time.time()

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
                    audio_chunk = self.audio_ring_buffer.get_recent(chunk_duration)
                    if len(audio_chunk) > 0 and self.vad.has_speech(audio_chunk):
                        try:
                            # Isola a voz cantante e atenua bumbo/baixo/pratos
                            filtered_chunk = apply_voice_bandpass_filter(audio_chunk)
                            context_prompt = self._build_context_prompt()
                            asr_res = self.transcription_engine.transcribe(filtered_chunk, prompt=context_prompt)
                            if asr_res.text:
                                self.rolling_transcript.add(asr_res.text, asr_res.timestamp)
                                full_transcript = self.rolling_transcript.get_text()

                                self.state.last_transcript_chunk = asr_res.text
                                self.state.rolling_transcript = full_transcript
                                self.state.inference_time_ms = asr_res.inference_time
                                if asr_res.duration > 0:
                                    self.state.rtf = round((asr_res.inference_time / 1000.0) / asr_res.duration, 2)
                                self.state.notify()

                                log_event("ASR", f"Transcrição: \"{asr_res.text}\" ({asr_res.inference_time:.0f}ms)")
                                self._process_matching_and_decision(full_transcript, recent_transcript=asr_res.text)
                        except Exception as e:
                            log_event("ASR", f"Erro no processamento do chunk: {e}", level=30)

                elapsed = time.time() - loop_start
                sleep_time = max(0.05, step_interval - elapsed)
                time.sleep(sleep_time)

        self._worker_thread = threading.Thread(target=_worker_loop, daemon=True)
        self._worker_thread.start()

    def _process_matching_and_decision(self, transcript: str, recent_transcript: str = "") -> None:
        """Compara o texto com a playlist, avalia candidatos e aciona o Holyrics se apropriado."""
        if self.state.current_song is None and self.state.playlist.songs:
            search_text = f"{transcript} {recent_transcript}".strip()
            song_res = self.matcher.match_song(search_text, self.state.playlist)
            if song_res.is_confident and song_res.song:
                self.state.current_song = song_res.song
                self.state.notify()
                log_event("MATCHER", f"Música identificada: '{song_res.song.title}' (Score: {song_res.score:.1f}%)")
                if self.state.automation_mode == "AUTOMATICO" and not self.state.manual_override_active:
                    try:
                        self.holyrics_service.client.show_lyrics_sync(song_res.song.id)
                    except Exception as e:
                        log_event("HOLYRICS", f"Erro ao enviar ShowLyrics: {e}", level=30)

        if self.state.current_song and self.state.current_song.slides:
            slide_res = self.matcher.match_slide(
                transcript=transcript,
                song=self.state.current_song,
                current_slide_index=self.state.current_slide_index,
                recent_transcript=recent_transcript,
            )

            best_cand = slide_res.best_candidate

            # Se o score na música atual for baixo (< 60%), verifica se uma nova música da playlist começou
            if (not best_cand or best_cand.score < 60.0) and len(self.state.playlist.songs) > 1:
                alt_song_res = self.matcher.match_song(transcript, self.state.playlist)
                if alt_song_res.is_confident and alt_song_res.song and alt_song_res.song.id != self.state.current_song.id:
                    log_event("MATCHER", f"Troca de música detectada: '{alt_song_res.song.title}' (Score: {alt_song_res.score:.1f}%)")
                    self.state.current_song = alt_song_res.song
                    self.state.current_slide_index = None
                    self.state.current_slide_number = None
                    self.state.notify()
                    if self.state.automation_mode == "AUTOMATICO" and not self.state.manual_override_active:
                        try:
                            self.holyrics_service.client.show_lyrics_sync(alt_song_res.song.id, initial_index=0)
                        except Exception as e:
                            log_event("HOLYRICS", f"Erro ao trocar música via ShowLyrics: {e}", level=30)
                    return

            if best_cand:
                self.state.candidate_slide_index = best_cand.slide_index
                self.state.candidate_slide_text = best_cand.text
                self.state.candidate_score = best_cand.score

                dec_res = self.decision_engine.evaluate(
                    candidate_index=best_cand.slide_index,
                    candidate_score=best_cand.score,
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

