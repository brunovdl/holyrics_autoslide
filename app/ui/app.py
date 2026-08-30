"""Aplicação principal Flet com NavigationRail e tema escuro."""
from __future__ import annotations

import asyncio
import flet as ft

from app.config.settings import AppSettings
from app.models.app_state import AppState
from app.holyrics.client import HolyricsClient
from app.holyrics.service import HolyricsService
from app.services.automation_service import AutomationService
from app.services.playlist_service import PlaylistService
from app.utils.logging import setup_logger, log_event

from app.ui.dashboard import DashboardPage
from app.ui.audio_page import AudioPage
from app.ui.holyrics_page import HolyricsPage
from app.ui.transcription_page import TranscriptionPage
from app.ui.settings_page import SettingsPage
from app.ui.logs_page import LogsPage


class HolyricsAutoSlideApp:
    """Gerenciador principal da interface gráfica e ciclo de vida da aplicação."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.page.title = "Holyrics AutoSlide — Transcrição & Controle Autônomo"
        self.page.theme_mode = ft.ThemeMode.DARK
        if hasattr(self.page, "window"):
            self.page.window.width = 1100
            self.page.window.height = 750
            self.page.window.min_width = 900
            self.page.window.min_height = 600

        setup_logger()

        # 1. Carrega configurações e inicializa estado
        self.settings = AppSettings.load()
        self.state = AppState()

        # 2. Inicializa serviços
        self.client = HolyricsClient(
            host=self.settings.holyrics.host,
            port=self.settings.holyrics.port,
            token=self.settings.holyrics.token,
            timeout=self.settings.holyrics.timeout,
        )
        self.holyrics_service = HolyricsService(client=self.client, state=self.state)
        self.playlist_service = PlaylistService(holyrics_service=self.holyrics_service, state=self.state)
        self.automation_service = AutomationService(
            settings=self.settings,
            state=self.state,
            holyrics_service=self.holyrics_service,
        )

        # 3. Páginas da UI
        self.dashboard_page = DashboardPage(
            state=self.state,
            automation_service=self.automation_service,
            holyrics_service=self.holyrics_service,
        )
        self.audio_page = AudioPage(
            state=self.state,
            settings=self.settings,
            automation_service=self.automation_service,
        )
        self.holyrics_page = HolyricsPage(
            state=self.state,
            settings=self.settings,
            holyrics_service=self.holyrics_service,
        )
        self.transcription_page = TranscriptionPage(
            state=self.state,
            settings=self.settings,
            automation_service=self.automation_service,
        )
        self.settings_page = SettingsPage(state=self.state, settings=self.settings)
        self.logs_page = LogsPage(state=self.state)

        self.pages_list = [
            self.dashboard_page,
            self.audio_page,
            self.holyrics_page,
            self.transcription_page,
            self.settings_page,
            self.logs_page,
        ]

        self.current_page_container = ft.Container(
            content=self.dashboard_page,
            expand=True,
        )

        # 4. NavigationRail lateral
        self.rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            min_extended_width=200,
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.DASHBOARD_OUTLINED,
                    selected_icon=ft.Icons.DASHBOARD,
                    label="Dashboard",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.MIC_NONE,
                    selected_icon=ft.Icons.MIC,
                    label="Áudio",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.QUEUE_MUSIC_OUTLINED,
                    selected_icon=ft.Icons.QUEUE_MUSIC,
                    label="Holyrics",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.RECORD_VOICE_OVER_OUTLINED,
                    selected_icon=ft.Icons.RECORD_VOICE_OVER,
                    label="Whisper",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.TUNE_OUTLINED,
                    selected_icon=ft.Icons.TUNE,
                    label="Ajustes",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.RECEIPT_LONG_OUTLINED,
                    selected_icon=ft.Icons.RECEIPT_LONG,
                    label="Logs",
                ),
            ],
            on_change=self._on_nav_change,
        )

        # Registra observador do AppState
        self.state.add_listener(self._on_state_change)

        # Monta a estrutura da página
        self.page.add(
            ft.Row(
                [
                    self.rail,
                    ft.VerticalDivider(width=1),
                    self.current_page_container,
                ],
                expand=True,
            )
        )

        # Inicia serviços em background
        asyncio.create_task(self._startup())

    def _on_nav_change(self, e: ft.ControlEvent) -> None:
        idx = int(e.control.selected_index) if e.control.selected_index is not None else int(e.data)
        self.rail.selected_index = idx
        self.current_page_container.content = self.pages_list[idx]
        self.pages_list[idx].update_ui()
        try:
            self.page.update()
        except Exception:
            pass

    def _on_state_change(self, _: AppState) -> None:
        """Propaga atualizações de estado para a página visível no momento."""
        current_idx = self.rail.selected_index or 0
        if 0 <= current_idx < len(self.pages_list):
            self.pages_list[current_idx].update_ui()

    async def _ui_tick_loop(self) -> None:
        """Loop periódico para garantir sincronização e re-renderização suave da UI web."""
        while True:
            await asyncio.sleep(0.4)
            try:
                current_idx = self.rail.selected_index or 0
                if 0 <= current_idx < len(self.pages_list):
                    self.pages_list[current_idx].update_ui()
                self.page.update()
            except Exception:
                pass

    async def _startup(self) -> None:
        """Inicialização dos serviços."""
        log_event("APP", "Iniciando Holyrics AutoSlide...")

        await self.holyrics_service.start_polling(interval=self.settings.holyrics.poll_interval)
        await self.playlist_service.start(interval=self.settings.holyrics.playlist_poll_interval)

        try:
            await self.holyrics_service.fetch_playlist()
        except Exception:
            pass

        try:
            self.automation_service.start_audio()
        except Exception:
            pass

        self.automation_service.start_worker()
        self._tick_task = asyncio.create_task(self._ui_tick_loop())

    async def shutdown(self) -> None:
        """Encerramento seguro de todos os serviços."""
        log_event("APP", "Encerrando Holyrics AutoSlide...")
        if hasattr(self, "_tick_task") and self._tick_task:
            self._tick_task.cancel()
        self.automation_service.stop_worker()
        self.automation_service.stop_audio()
        await self.holyrics_service.stop_polling()
        await self.playlist_service.stop()
        await self.client.close()
        self.settings.save()

