"""Serviço de gerenciamento de dados e sincronização com o Holyrics."""
from __future__ import annotations

import asyncio
import time
import httpx
from typing import Callable

from app.holyrics.client import HolyricsClient
from app.models.song import Song, PlaylistSnapshot
from app.models.slide import SongSlide
from app.models.app_state import AppState
from app.utils.logging import log_event


class HolyricsService:
    """Gerencia polling de apresentação, cache de letras e sincronia com o Holyrics."""

    def __init__(self, client: HolyricsClient, state: AppState) -> None:
        self.client = client
        self.state = state
        self._poll_task: asyncio.Task | None = None
        self._running = False
        self._cached_songs: dict[str, Song] = {}
        self.on_manual_slide_change: Callable[[int], None] | None = None
        self.on_song_change: Callable[[Song, bool], None] | None = None
        self._pending_commands: dict[int, float] = {}
        self._last_song_cmd_time = 0.0
        self._last_song_cmd_id: str | None = None

    def mark_command_sent(self, slide_index: int) -> None:
        """Registra que um comando de troca de slide foi enviado pela automação."""
        now = time.time()
        self._pending_commands[slide_index] = now
        # Limpa comandos expirados (> 4.0s)
        self._pending_commands = {k: v for k, v in self._pending_commands.items() if now - v < 4.0}

    def mark_song_command_sent(self, song_id: str) -> None:
        """Registra que um comando de troca de música foi enviado pela automação."""
        self._last_song_cmd_time = time.time()
        self._last_song_cmd_id = song_id

    async def fetch_playlist(self) -> PlaylistSnapshot:
        """Carrega todas as músicas da playlist do Holyrics com seus respectivos slides."""
        try:
            items = await self.client.get_lyrics_playlist()
            songs: list[Song] = []
            for item in items:
                song_id_str = str(item.id)
                if song_id_str in self._cached_songs and len(self._cached_songs[song_id_str].slides) > 0:
                    songs.append(self._cached_songs[song_id_str])
                    continue

                try:
                    details = await self.client.get_lyrics(song_id_str)
                    slides: list[SongSlide] = []
                    for idx, s in enumerate(details.slides):
                        text = s.text.strip()
                        if not text:
                            continue
                        words = text.split()[:4]
                        start_words = " ".join(words)
                        slides.append(
                            SongSlide(
                                index=idx,
                                text=text,
                                start_words=start_words,
                            )
                        )

                    full_text = " ".join([s.text for s in slides])
                    song = Song(
                        id=song_id_str,
                        title=details.title or item.title,
                        artist=details.artist or item.artist,
                        slides=slides,
                        full_text=full_text,
                    )
                    if len(slides) > 0:
                        self._cached_songs[song_id_str] = song
                    songs.append(song)
                except Exception as e:
                    log_event("HOLYRICS", f"Erro ao obter letra da música {item.title}: {e}", level=30)

            snapshot = PlaylistSnapshot(songs=songs, last_updated=time.time())
            self.state.playlist = snapshot
            self.state.notify()
            total_slides = sum(len(s.slides) for s in songs)
            log_event("HOLYRICS", f"Playlist carregada: {len(songs)} música(s), {total_slides} slide(s) total")
            return snapshot
        except Exception as e:
            log_event("HOLYRICS", f"Falha ao carregar playlist: {e}", level=40)
            raise

    async def sync_current_presentation(self) -> None:
        """Consulta a apresentação atual e sincroniza com o AppState."""
        try:
            curr = await self.client.get_current_presentation()
            self._consecutive_poll_failures = 0
            was_disconnected = not self.state.holyrics_connected
            self.state.holyrics_connected = True

            # Se a playlist estiver vazia e o Holyrics acabou de conectar, busca as músicas
            if (was_disconnected or not self.state.playlist.songs) and not getattr(self, "_is_fetching_playlist", False):
                self._is_fetching_playlist = True

                async def _auto_fetch() -> None:
                    try:
                        await self.fetch_playlist()
                    except Exception:
                        pass
                    finally:
                        self._is_fetching_playlist = False

                asyncio.create_task(_auto_fetch())

            # Procura a música na playlist pelo ID ou pelo Título
            matched_song = None
            if curr.id:
                matched_song = self.state.playlist.get_song_by_id(str(curr.id))
            if not matched_song and curr.title:
                matched_song = self.state.playlist.get_song_by_title(curr.title)

            new_song = matched_song or (
                Song(
                    id=str(curr.id) if curr.id else "",
                    title=curr.title or "Apresentação Atual",
                    artist=curr.artist or "",
                    slides=[],
                )
                if (curr.id or curr.title)
                else None
            )

            if not new_song and not self.state.current_song and len(self.state.playlist.songs) == 1:
                new_song = self.state.playlist.songs[0]

            if new_song:
                old_song = self.state.current_song
                if not old_song or old_song.id != new_song.id or old_song.title != new_song.title:
                    now = time.time()
                    is_app_sent_song = (
                        now - self._last_song_cmd_time < 2.5
                        and self._last_song_cmd_id == new_song.id
                    )
                    self.state.current_song = new_song
                    if self.on_song_change:
                        self.on_song_change(new_song, not is_app_sent_song)

            if not curr.is_active and not self.state.current_song:
                self.state.holyrics_status = "OCIOSO"
                self.state.current_slide_index = None
                self.state.current_slide_number = None
                self.state.current_slide_text = ""
                self.state.notify()
                return

            self.state.holyrics_status = "PROJETANDO"

            slide_raw = curr.slide
            if slide_raw is not None:
                slide_0_based = max(0, slide_raw - 1) if slide_raw > 0 else slide_raw
                slide_1_based = slide_0_based + 1
            elif self.state.current_slide_index is not None:
                slide_0_based = self.state.current_slide_index
                slide_1_based = self.state.current_slide_index + 1
            else:
                slide_0_based = None
                slide_1_based = None

            if (
                slide_0_based is not None
                and self.state.current_slide_index is not None
                and slide_0_based != self.state.current_slide_index
            ):
                now = time.time()
                cmd_sent_time = self._pending_commands.get(slide_0_based)
                is_recent_app_command = cmd_sent_time is not None and (now - cmd_sent_time) < 3.5

                if is_recent_app_command:
                    self._pending_commands.pop(slide_0_based, None)
                else:
                    log_event(
                        "HOLYRICS",
                        f"Intervenção manual detectada: Holyrics mudou para slide {slide_1_based}",
                    )
                    if self.on_manual_slide_change:
                        self.on_manual_slide_change(slide_0_based)

            if slide_0_based is not None:
                self.state.current_slide_index = slide_0_based
                self.state.current_slide_number = slide_1_based

            if curr.total_slides:
                self.state.total_slides = curr.total_slides
            elif self.state.current_song:
                self.state.total_slides = len(self.state.current_song.slides)

            if self.state.current_song and self.state.current_slide_index is not None and 0 <= self.state.current_slide_index < len(self.state.current_song.slides):
                self.state.current_slide_text = self.state.current_song.slides[self.state.current_slide_index].text

            self.state.notify()
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException, ConnectionRefusedError, OSError) as e:
            self._consecutive_poll_failures = getattr(self, "_consecutive_poll_failures", 0) + 1
            if self._consecutive_poll_failures >= 3:
                if self.state.holyrics_connected or self.state.holyrics_status != "DESCONECTADO":
                    self.state.holyrics_connected = False
                    self.state.holyrics_status = "DESCONECTADO"
                    self.state.notify()
                    log_event("HOLYRICS", f"Holyrics inacessível / desconectado: {e}", level=30)
        except Exception:
            pass

    async def start_polling(self, interval: float = 0.5) -> None:
        """Inicia tarefa assíncrona de sincronização contínua."""
        if self._running:
            return
        self._running = True

        async def _loop() -> None:
            while self._running:
                await self.sync_current_presentation()
                await asyncio.sleep(interval)

        self._poll_task = asyncio.create_task(_loop())

    async def stop_polling(self) -> None:
        """Para a tarefa de sincronização."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None

