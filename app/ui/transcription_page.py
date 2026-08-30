"""Página de transcrição e visualização de inferência do Faster-Whisper."""
from __future__ import annotations

import flet as ft
from app.models.app_state import AppState
from app.config.settings import AppSettings
from app.services.automation_service import AutomationService


class TranscriptionPage(ft.Container):
    """Configuração e monitoramento do motor Whisper."""

    def __init__(
        self,
        state: AppState,
        settings: AppSettings,
        automation_service: AutomationService,
    ) -> None:
        super().__init__(expand=True, padding=20)
        self.state = state
        self.settings = settings
        self.automation = automation_service

        self.groq_key_input = ft.TextField(
            label="Groq API Key",
            value=self.settings.transcription.groq_api_key,
            password=True,
            can_reveal_password=True,
            expand=True,
            on_change=self._on_groq_key_changed,
        )

        self.model_dropdown = ft.Dropdown(
            label="Modelo de Transcrição Groq Cloud",
            value=self.settings.transcription.groq_model,
            options=[
                ft.dropdown.Option("whisper-large-v3-turbo", "whisper-large-v3-turbo (Ultra-rápido ~100-200ms)"),
                ft.dropdown.Option("whisper-large-v3", "whisper-large-v3 (Precisão Máxima)"),
            ],
            expand=True,
            on_select=self._on_model_changed,
        )

        self.vad_switch = ft.Switch(
            label="Ativar VAD (Detecção de Atividade de Voz)",
            value=self.settings.transcription.vad_enabled,
            on_change=self._on_vad_changed,
        )

        self.metrics_text = ft.Text("Inferência: 0 ms | RTF: 0.00", size=13, color=ft.Colors.GREEN_300)
        self.live_transcript_box = ft.Text("Aguardando áudio...", size=14, color=ft.Colors.YELLOW_100)

        self.content = self._build_layout()

    def _build_layout(self) -> ft.Control:
        return ft.Column(
            [
                ft.Text("TRANSCRIÇÃO EM NUVEM GROQ (WHISPER AI)", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Inferência de áudio em nuvem de ultra-baixa latência com whisper-large-v3-turbo.",
                    color=ft.Colors.GREY_400,
                ),
                ft.Divider(),
                ft.Card(
                    content=ft.Container(
                        padding=20,
                        content=ft.Column(
                            [
                                ft.Row([self.groq_key_input]),
                                ft.Row([self.model_dropdown, self.vad_switch]),
                            ],
                            spacing=15,
                        ),
                    )
                ),
                ft.Card(
                    expand=True,
                    content=ft.Container(
                        padding=20,
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text("TRANSCRIÇÃO EM TEMPO REAL", size=14, weight=ft.FontWeight.BOLD),
                                        self.metrics_text,
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                ft.Container(
                                    content=self.live_transcript_box,
                                    padding=15,
                                    bgcolor=ft.Colors.GREY_900,
                                    border_radius=8,
                                    expand=True,
                                ),
                            ],
                            spacing=10,
                            expand=True,
                        ),
                    ),
                ),
            ],
            spacing=15,
            expand=True,
        )

    def _on_groq_key_changed(self, e: ft.ControlEvent) -> None:
        self.settings.transcription.groq_api_key = e.control.value.strip()
        self.settings.save()
        if hasattr(self.automation.transcription_engine, "api_key"):
            self.automation.transcription_engine.api_key = e.control.value.strip()
            self.automation.transcription_engine.load_model()

    def _on_model_changed(self, e: ft.ControlEvent) -> None:
        self.settings.transcription.groq_model = e.control.value
        self.settings.transcription.model = e.control.value
        self.settings.save()
        if hasattr(self.automation.transcription_engine, "model"):
            self.automation.transcription_engine.model = e.control.value

    def _on_vad_changed(self, e: ft.ControlEvent) -> None:
        self.settings.transcription.vad_enabled = e.control.value
        self.automation.vad.enabled = e.control.value
        self.settings.save()

    def update_ui(self) -> None:
        self.metrics_text.value = f"Inferência Groq: {self.state.inference_time_ms:.1f} ms | RTF: {self.state.rtf:.2f}"
        self.live_transcript_box.value = self.state.rolling_transcript or "Aguardando áudio..."
        try:
            self.update()
        except (RuntimeError, Exception):
            pass

