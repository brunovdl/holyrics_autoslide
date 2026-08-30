"""Página principal de Dashboard e visualização em tempo real."""
from __future__ import annotations

import asyncio
import flet as ft

from app.models.app_state import AppState
from app.services.automation_service import AutomationService
from app.holyrics.service import HolyricsService


class DashboardPage(ft.Container):
    """Visualização consolidada com métricas de apresentação, VU, transcrição e controles."""

    def __init__(
        self,
        state: AppState,
        automation_service: AutomationService,
        holyrics_service: HolyricsService,
    ) -> None:
        super().__init__(expand=True, padding=20)
        self.state = state
        self.automation = automation_service
        self.holyrics = holyrics_service

        self.holyrics_status = ft.Text("Desconectado", color=ft.Colors.RED_400, weight=ft.FontWeight.BOLD)
        self.audio_status = ft.Text("Parado", color=ft.Colors.GREY_400, weight=ft.FontWeight.BOLD)
        self.whisper_status = ft.Text("Carregando...", color=ft.Colors.AMBER_400, weight=ft.FontWeight.BOLD)
        self.mode_status = ft.Text("PARADO", color=ft.Colors.BLUE_GREY_300, weight=ft.FontWeight.BOLD)

        self.song_title_text = ft.Text("Nenhuma música ativa", size=18, weight=ft.FontWeight.BOLD)
        self.song_artist_text = ft.Text("—", size=14, color=ft.Colors.GREY_400)
        self.slide_counter_text = ft.Text("Slide 0 / 0", size=16, color=ft.Colors.LIGHT_BLUE_300)

        self.current_slide_display = ft.Text("—", size=14, italic=True)
        self.candidate_slide_display = ft.Text("—", size=14, color=ft.Colors.GREEN_300, weight=ft.FontWeight.W_500)
        self.candidate_score_display = ft.Text("Score: 0% | Confirmações: 0/2", size=12, color=ft.Colors.GREY_400)

        self.transcript_text = ft.Text("Aguardando áudio...", size=14, color=ft.Colors.YELLOW_200)

        self.vu_bar = ft.ProgressBar(value=0.0, height=8, color=ft.Colors.GREEN_400, bgcolor=ft.Colors.GREY_800)
        self.vu_label = ft.Text("-60.0 dB", size=12, color=ft.Colors.GREY_400)

        self.manual_override_banner = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.AMBER_900),
                    ft.Text(
                        "Intervenção manual detectada no Holyrics! Automação pausada temporariamente.",
                        color=ft.Colors.AMBER_100,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=ft.Colors.AMBER_800,
            padding=10,
            border_radius=8,
            visible=False,
        )

        self.content = self._build_layout()

    def _set_mode(self, mode: str) -> None:
        self.automation.set_mode(mode)
        self.update_ui()

    def _on_reconnect_clicked(self, _: ft.ControlEvent) -> None:
        async def _reconnect() -> None:
            self.holyrics_status.value = "Conectando..."
            self.holyrics_status.color = ft.Colors.AMBER_400
            try:
                self.update()
                if self.page:
                    self.page.update()
            except Exception:
                pass
            await self.holyrics.client.reset_client()
            await self.holyrics.sync_current_presentation()
            try:
                await self.holyrics.fetch_playlist()
            except Exception:
                pass
            self.update_ui()

        asyncio.create_task(_reconnect())

    def _build_layout(self) -> ft.Control:
        top_bar = ft.Card(
            content=ft.Container(
                padding=15,
                content=ft.Row(
                    [
                        ft.Row([ft.Icon(ft.Icons.CLOUD, size=18), ft.Text("Holyrics:"), self.holyrics_status]),
                        ft.Row([ft.Icon(ft.Icons.MIC, size=18), ft.Text("Áudio:"), self.audio_status]),
                        ft.Row([ft.Icon(ft.Icons.RECORD_VOICE_OVER, size=18), ft.Text("Whisper:"), self.whisper_status]),
                        ft.Row([ft.Icon(ft.Icons.TUNE, size=18), ft.Text("Modo:"), self.mode_status]),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                ),
            )
        )

        controls_row = ft.Row(
            [
                ft.Button(
                    "Reconectar",
                    icon=ft.Icons.SYNC,
                    bgcolor=ft.Colors.BLUE_GREY_800,
                    color=ft.Colors.WHITE,
                    tooltip="Forçar reconexão com o Holyrics e atualizar dados",
                    on_click=self._on_reconnect_clicked,
                ),
                ft.Button(
                    "Iniciar Monitor",
                    icon=ft.Icons.VISIBILITY,
                    bgcolor=ft.Colors.INDIGO_700,
                    color=ft.Colors.WHITE,
                    on_click=lambda _: self._set_mode("MONITOR"),
                ),
                ft.Button(
                    "Ativar Automático",
                    icon=ft.Icons.PLAY_ARROW,
                    bgcolor=ft.Colors.GREEN_700,
                    color=ft.Colors.WHITE,
                    on_click=lambda _: self._set_mode("AUTOMATICO"),
                ),
                ft.OutlinedButton(
                    "Parar",
                    icon=ft.Icons.STOP,
                    on_click=lambda _: self._set_mode("PARADO"),
                ),
                ft.IconButton(
                    icon=ft.Icons.SKIP_PREVIOUS,
                    tooltip="Slide Anterior",
                    on_click=lambda _: asyncio.create_task(self.holyrics.client.previous()),
                ),
                ft.IconButton(
                    icon=ft.Icons.SKIP_NEXT,
                    tooltip="Próximo Slide",
                    on_click=lambda _: asyncio.create_task(self.holyrics.client.next()),
                ),
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    tooltip="Atualizar Playlist",
                    on_click=lambda _: asyncio.create_task(self.holyrics.fetch_playlist()),
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
        )

        presentation_card = ft.Card(
            expand=1,
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Text("MÚSICA ATUAL", size=12, color=ft.Colors.GREY_400, weight=ft.FontWeight.BOLD),
                        self.song_title_text,
                        self.song_artist_text,
                        ft.Divider(),
                        self.slide_counter_text,
                        ft.Text("Slide Atual:", size=12, color=ft.Colors.GREY_400),
                        self.current_slide_display,
                        ft.Divider(),
                        ft.Text("Próximo Candidato:", size=12, color=ft.Colors.GREEN_400),
                        self.candidate_slide_display,
                        self.candidate_score_display,
                    ],
                    spacing=6,
                ),
            ),
        )

        audio_card = ft.Card(
            expand=1,
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Text("NÍVEL DE ÁUDIO (VU METER)", size=12, color=ft.Colors.GREY_400, weight=ft.FontWeight.BOLD),
                        ft.Row([self.vu_bar, self.vu_label], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Divider(),
                        ft.Text("TRANSCRIÇÃO EM TEMPO REAL", size=12, color=ft.Colors.GREY_400, weight=ft.FontWeight.BOLD),
                        ft.Container(
                            content=self.transcript_text,
                            padding=10,
                            bgcolor=ft.Colors.GREY_900,
                            border_radius=8,
                            height=120,
                        ),
                    ],
                    spacing=8,
                ),
            ),
        )

        return ft.Column(
            [
                top_bar,
                self.manual_override_banner,
                ft.Row([presentation_card, audio_card], spacing=15, expand=True),
                controls_row,
            ],
            spacing=15,
            expand=True,
        )

    def update_ui(self) -> None:
        h_status = getattr(self.state, "holyrics_status", "DESCONECTADO" if not self.state.holyrics_connected else "PROJETANDO")
        if h_status == "PROJETANDO":
            self.holyrics_status.value = "Conectado (Projetando)"
            self.holyrics_status.color = ft.Colors.GREEN_400
        elif h_status == "OCIOSO":
            self.holyrics_status.value = "Conectado (Ocioso)"
            self.holyrics_status.color = ft.Colors.AMBER_400
        else:
            self.holyrics_status.value = "Desconectado"
            self.holyrics_status.color = ft.Colors.RED_400

        if self.state.audio_capturing:
            self.audio_status.value = "Capturando"
            self.audio_status.color = ft.Colors.GREEN_400
        else:
            self.audio_status.value = "Parado"
            self.audio_status.color = ft.Colors.GREY_400

        if self.state.transcriber_ready:
            self.whisper_status.value = "Groq Cloud Pronta"
            self.whisper_status.color = ft.Colors.GREEN_400
        else:
            self.whisper_status.value = "Aguardando chave Groq..."
            self.whisper_status.color = ft.Colors.AMBER_400

        self.mode_status.value = self.state.automation_mode
        if self.state.automation_mode == "AUTOMATICO":
            self.mode_status.color = ft.Colors.GREEN_400
        elif self.state.automation_mode == "MONITOR":
            self.mode_status.color = ft.Colors.INDIGO_300
        else:
            self.mode_status.color = ft.Colors.GREY_400

        if self.state.current_song:
            self.song_title_text.value = self.state.current_song.title
            self.song_artist_text.value = self.state.current_song.artist or "—"
            curr_slide_num = (self.state.current_slide_index + 1) if self.state.current_slide_index is not None else 0
            self.slide_counter_text.value = f"Slide {curr_slide_num} / {len(self.state.current_song.slides)}"
            self.current_slide_display.value = self.state.current_slide_text or "—"
        else:
            self.song_title_text.value = "Nenhuma música ativa"
            self.song_artist_text.value = "—"
            self.slide_counter_text.value = "Slide 0 / 0"
            self.current_slide_display.value = "—"

        if self.state.candidate_slide_index is not None:
            cand_num = self.state.candidate_slide_index + 1
            self.candidate_slide_display.value = f"Slide {cand_num}: {self.state.candidate_slide_text[:60]}..."
            self.candidate_score_display.value = (
                f"Score: {self.state.candidate_score:.1f}% | "
                f"Confirmações: {self.state.candidate_hits}/{self.state.required_hits}"
            )
        else:
            self.candidate_slide_display.value = "—"
            self.candidate_score_display.value = "Score: 0% | Confirmações: 0/2"

        self.transcript_text.value = f'"{self.state.rolling_transcript}"' if self.state.rolling_transcript else "Aguardando áudio..."

        db = self.state.audio_peak_db
        normalized_vu = max(0.0, min(1.0, (db + 60.0) / 60.0))
        self.vu_bar.value = normalized_vu
        self.vu_label.value = f"{db:.1f} dB"

        if self.state.manual_override_active:
            self.manual_override_banner.visible = True
            self.manual_override_banner.content.controls[1].value = (
                f"Intervenção manual detectada no Holyrics! Automação pausada ({self.state.manual_override_remaining:.1f}s)"
            )
        else:
            self.manual_override_banner.visible = False

        try:
            self.update()
        except (RuntimeError, Exception):
            pass

