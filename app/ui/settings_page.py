"""Página de ajustes de thresholds, cooldown, antecipação e restauração de padrões."""
from __future__ import annotations

import flet as ft
from app.models.app_state import AppState
from app.config.settings import AppSettings
from app.config.defaults import (
    DEFAULT_SONG_THRESHOLD,
    DEFAULT_SONG_MARGIN,
    DEFAULT_SLIDE_THRESHOLD_STRONG,
    DEFAULT_SLIDE_THRESHOLD_POSSIBLE,
    DEFAULT_CONSECUTIVE_CONFIRMATIONS,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_MANUAL_PAUSE_SECONDS,
    DEFAULT_ANTICIPATION_MODE,
)


class SettingsPage(ft.Container):
    """Calibração das heurísticas do motor de decisão."""

    def __init__(self, state: AppState, settings: AppSettings) -> None:
        super().__init__(expand=True, padding=20)
        self.state = state
        self.settings = settings

        self.song_threshold_slider = ft.Slider(
            min=50,
            max=99,
            divisions=49,
            value=self.settings.decision.song_threshold,
            label="{value}%",
            on_change=self._on_song_thresh_change,
        )
        self.song_threshold_val = ft.Text(f"{self.settings.decision.song_threshold:.0f}%", weight=ft.FontWeight.BOLD)

        self.slide_strong_slider = ft.Slider(
            min=60,
            max=99,
            divisions=39,
            value=self.settings.decision.slide_threshold_strong,
            label="{value}%",
            on_change=self._on_slide_strong_change,
        )
        self.slide_strong_val = ft.Text(f"{self.settings.decision.slide_threshold_strong:.0f}%", weight=ft.FontWeight.BOLD)

        self.confirmations_slider = ft.Slider(
            min=1,
            max=5,
            divisions=4,
            value=self.settings.decision.consecutive_confirmations,
            label="{value}",
            on_change=self._on_conf_change,
        )
        self.confirmations_val = ft.Text(str(self.settings.decision.consecutive_confirmations), weight=ft.FontWeight.BOLD)

        self.cooldown_slider = ft.Slider(
            min=0.3,
            max=3.0,
            divisions=27,
            value=self.settings.decision.cooldown_seconds,
            label="{value}s",
            on_change=self._on_cooldown_change,
        )
        self.cooldown_val = ft.Text(f"{self.settings.decision.cooldown_seconds:.1f}s", weight=ft.FontWeight.BOLD)

        self.anticipation_dropdown = ft.Dropdown(
            label="Modo de Troca / Antecipação",
            value=self.settings.decision.anticipation_mode,
            options=[
                ft.dropdown.Option("conservador", "Conservador (Exige maior confirmação da frase)"),
                ft.dropdown.Option("equilibrado", "Equilibrado (Recomendado)"),
                ft.dropdown.Option("antecipado", "Antecipado (Troca ao detectar início do slide)"),
            ],
            expand=True,
            on_select=self._on_anticipation_change,
        )

        self.restore_button = ft.OutlinedButton(
            "Restaurar Padrões",
            icon=ft.Icons.RESTORE,
            on_click=self._restore_defaults,
        )

        self.content = self._build_layout()

    def _build_layout(self) -> ft.Control:
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("AJUSTES E CALIBRAÇÃO DE DECISÃO", size=20, weight=ft.FontWeight.BOLD),
                                ft.Text("Calibre a sensibilidade e estabilidade do motor de troca.", color=ft.Colors.GREY_400),
                            ]
                        ),
                        self.restore_button,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(),
                ft.Card(
                    content=ft.Container(
                        padding=20,
                        content=ft.Column(
                            [
                                ft.Text("Threshold Mínimo de Identificação de Música:", size=13, weight=ft.FontWeight.W_500),
                                ft.Row([self.song_threshold_slider, self.song_threshold_val]),
                                ft.Divider(),
                                ft.Text("Threshold de Troca Forte de Slide:", size=13, weight=ft.FontWeight.W_500),
                                ft.Row([self.slide_strong_slider, self.slide_strong_val]),
                                ft.Divider(),
                                ft.Text("Confirmações Consecutivas Necessárias:", size=13, weight=ft.FontWeight.W_500),
                                ft.Row([self.confirmations_slider, self.confirmations_val]),
                                ft.Divider(),
                                ft.Text("Cooldown Pós-Troca de Slide (Segurança):", size=13, weight=ft.FontWeight.W_500),
                                ft.Row([self.cooldown_slider, self.cooldown_val]),
                                ft.Divider(),
                                self.anticipation_dropdown,
                            ],
                            spacing=8,
                        ),
                    )
                ),
            ],
            spacing=15,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _on_song_thresh_change(self, e: ft.ControlEvent) -> None:
        val = round(float(e.control.value), 1)
        self.settings.decision.song_threshold = val
        self.song_threshold_val.value = f"{val:.0f}%"
        self.settings.save()
        self.update()

    def _on_slide_strong_change(self, e: ft.ControlEvent) -> None:
        val = round(float(e.control.value), 1)
        self.settings.decision.slide_threshold_strong = val
        self.slide_strong_val.value = f"{val:.0f}%"
        self.settings.save()
        self.update()

    def _on_conf_change(self, e: ft.ControlEvent) -> None:
        val = int(e.control.value)
        self.settings.decision.consecutive_confirmations = val
        self.confirmations_val.value = str(val)
        self.settings.save()
        self.update()

    def _on_cooldown_change(self, e: ft.ControlEvent) -> None:
        val = round(float(e.control.value), 1)
        self.settings.decision.cooldown_seconds = val
        self.cooldown_val.value = f"{val:.1f}s"
        self.settings.save()
        self.update()

    def _on_anticipation_change(self, e: ft.ControlEvent) -> None:
        self.settings.decision.anticipation_mode = e.control.value
        self.settings.save()

    def _restore_defaults(self, _: ft.ControlEvent) -> None:
        self.settings.decision.song_threshold = DEFAULT_SONG_THRESHOLD
        self.settings.decision.song_margin = DEFAULT_SONG_MARGIN
        self.settings.decision.slide_threshold_strong = DEFAULT_SLIDE_THRESHOLD_STRONG
        self.settings.decision.slide_threshold_possible = DEFAULT_SLIDE_THRESHOLD_POSSIBLE
        self.settings.decision.consecutive_confirmations = DEFAULT_CONSECUTIVE_CONFIRMATIONS
        self.settings.decision.cooldown_seconds = DEFAULT_COOLDOWN_SECONDS
        self.settings.decision.manual_pause_seconds = DEFAULT_MANUAL_PAUSE_SECONDS
        self.settings.decision.anticipation_mode = DEFAULT_ANTICIPATION_MODE

        self.song_threshold_slider.value = DEFAULT_SONG_THRESHOLD
        self.song_threshold_val.value = f"{DEFAULT_SONG_THRESHOLD:.0f}%"
        self.slide_strong_slider.value = DEFAULT_SLIDE_THRESHOLD_STRONG
        self.slide_strong_val.value = f"{DEFAULT_SLIDE_THRESHOLD_STRONG:.0f}%"
        self.confirmations_slider.value = DEFAULT_CONSECUTIVE_CONFIRMATIONS
        self.confirmations_val.value = str(DEFAULT_CONSECUTIVE_CONFIRMATIONS)
        self.cooldown_slider.value = DEFAULT_COOLDOWN_SECONDS
        self.cooldown_val.value = f"{DEFAULT_COOLDOWN_SECONDS:.1f}s"
        self.anticipation_dropdown.value = DEFAULT_ANTICIPATION_MODE

        self.settings.save()
        self.update()

    def update_ui(self) -> None:
        pass

