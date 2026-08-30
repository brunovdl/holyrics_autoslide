"""Página de logs estruturados e métricas de diagnóstico."""
from __future__ import annotations

import collections
import flet as ft
from app.models.app_state import AppState
from app.utils.logging import register_log_listener


class LogsPage(ft.Container):
    """Visualizador de eventos e telemetria do sistema."""

    def __init__(self, state: AppState) -> None:
        super().__init__(expand=True, padding=20)
        self.state = state
        self._logs: collections.deque[tuple[str, str, str]] = collections.deque(maxlen=300)

        self.logs_list_view = ft.ListView(expand=True, spacing=4, auto_scroll=True)
        self.category_filter = ft.Dropdown(
            label="Filtrar por Categoria",
            value="TODAS",
            options=[
                ft.dropdown.Option("TODAS", "Todas as Categorias"),
                ft.dropdown.Option("APP", "APP"),
                ft.dropdown.Option("AUDIO", "AUDIO"),
                ft.dropdown.Option("ASR", "ASR"),
                ft.dropdown.Option("MATCHER", "MATCHER"),
                ft.dropdown.Option("HOLYRICS", "HOLYRICS"),
                ft.dropdown.Option("DECISION", "DECISION"),
            ],
            width=200,
            on_select=lambda _: self._render_logs(),
        )

        self.clear_button = ft.OutlinedButton(
            "Limpar Logs",
            icon=ft.Icons.CLEAR_ALL,
            on_click=self._clear_logs,
        )

        register_log_listener(self._on_new_log)
        self.content = self._build_layout()

    def _build_layout(self) -> ft.Control:
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("LOGS DO SISTEMA E DIAGNÓSTICO", size=20, weight=ft.FontWeight.BOLD),
                                ft.Text("Histórico operacional estruturado e telemetria em tempo real.", color=ft.Colors.GREY_400),
                            ]
                        ),
                        ft.Row([self.category_filter, self.clear_button]),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(),
                ft.Card(
                    expand=True,
                    content=ft.Container(
                        padding=15,
                        bgcolor=ft.Colors.GREY_900,
                        border_radius=8,
                        content=self.logs_list_view,
                        expand=True,
                    ),
                ),
            ],
            spacing=15,
            expand=True,
        )

    def _on_new_log(self, category: str, level: str, msg: str) -> None:
        self._logs.append((category, level, msg))
        filter_cat = self.category_filter.value
        if filter_cat == "TODAS" or filter_cat == category:
            color = ft.Colors.GREY_300
            if level == "WARNING":
                color = ft.Colors.AMBER_300
            elif level in ("ERROR", "CRITICAL"):
                color = ft.Colors.RED_400
            elif category == "DECISION":
                color = ft.Colors.GREEN_300
            elif category == "MATCHER":
                color = ft.Colors.LIGHT_BLUE_300

            text_row = ft.Text(f"[{category}] {msg}", size=12, color=color, selectable=True)
            self.logs_list_view.controls.append(text_row)
            if len(self.logs_list_view.controls) > 300:
                self.logs_list_view.controls.pop(0)
            try:
                self.logs_list_view.update()
            except (RuntimeError, Exception):
                pass

    def _render_logs(self) -> None:
        self.logs_list_view.controls.clear()
        filter_cat = self.category_filter.value
        for cat, level, msg in self._logs:
            if filter_cat == "TODAS" or filter_cat == cat:
                color = ft.Colors.GREY_300
                if level == "WARNING":
                    color = ft.Colors.AMBER_300
                elif level in ("ERROR", "CRITICAL"):
                    color = ft.Colors.RED_400
                elif cat == "DECISION":
                    color = ft.Colors.GREEN_300
                elif cat == "MATCHER":
                    color = ft.Colors.LIGHT_BLUE_300
                self.logs_list_view.controls.append(
                    ft.Text(f"[{cat}] {msg}", size=12, color=color, selectable=True)
                )
        try:
            self.logs_list_view.update()
        except (RuntimeError, Exception):
            pass

    def _clear_logs(self, _: ft.ControlEvent) -> None:
        self._logs.clear()
        self.logs_list_view.controls.clear()
        try:
            self.logs_list_view.update()
        except (RuntimeError, Exception):
            pass

    def update_ui(self) -> None:
        pass

