"""Serviço de gerenciamento e cache da playlist ativa."""
from __future__ import annotations

import asyncio
from app.holyrics.service import HolyricsService
from app.models.app_state import AppState
from app.utils.logging import log_event


class PlaylistService:
    """Gerencia atualizações periódicas e sob demanda da playlist do Holyrics."""

    def __init__(self, holyrics_service: HolyricsService, state: AppState) -> None:
        self.holyrics_service = holyrics_service
        self.state = state
        self._running = False
        self._task: asyncio.Task | None = None

    async def refresh_playlist(self) -> None:
        """Atualiza a lista de músicas e letras da playlist."""
        await self.holyrics_service.fetch_playlist()

    async def start(self, interval: float = 3.0) -> None:
        """Inicia polling periódico da playlist."""
        if self._running:
            return
        self._running = True

        async def _poll_loop() -> None:
            while self._running:
                try:
                    await self.refresh_playlist()
                except Exception as e:
                    log_event("HOLYRICS", f"Erro no polling da playlist: {e}", level=30)
                await asyncio.sleep(interval)

        self._task = asyncio.create_task(_poll_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

