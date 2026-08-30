"""Página de configuração do Holyrics e gerenciamento de playlist."""
from __future__ import annotations

import asyncio
import flet as ft
from app.models.app_state import AppState
from app.config.settings import AppSettings
from app.holyrics.service import HolyricsService


class HolyricsPage(ft.Container):
    """Configuração de rede e visualização da playlist de músicas."""

    def __init__(
        self,
        state: AppState,
        settings: AppSettings,
        holyrics_service: HolyricsService,
    ) -> None:
        super().__init__(expand=True, padding=20)
        self.state = state
        self.settings = settings
        self.holyrics = holyrics_service

        self.host_input = ft.TextField(
            label="IP / Host do Holyrics",
            value=self.settings.holyrics.host,
            expand=True,
            on_change=self._on_host_changed,
        )

        self.port_input = ft.TextField(
            label="Porta",
            value=str(self.settings.holyrics.port),
            width=120,
            on_change=self._on_port_changed,
        )

        self.token_input = ft.TextField(
            label="Token da API Server",
            value=self.settings.holyrics.token,
            password=True,
            can_reveal_password=True,
            expand=True,
            on_change=self._on_token_changed,
        )

        self.test_conn_button = ft.Button(
            "Testar Conexão",
            icon=ft.Icons.NETWORK_CHECK,
            bgcolor=ft.Colors.INDIGO_700,
            color=ft.Colors.WHITE,
            on_click=self._on_test_connection,
        )

        self.conn_result_text = ft.Text("Status: Não verificado", color=ft.Colors.GREY_400)

        self.playlist_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Música")),
                ft.DataColumn(ft.Text("Artista")),
                ft.DataColumn(ft.Text("Slides")),
            ],
            rows=[],
            expand=True,
        )

        self.content = self._build_layout()

    def _build_layout(self) -> ft.Control:
        return ft.Column(
            [
                ft.Text("INTEGRAÇÃO COM O HOLYRICS", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Configure o endereço IP e token do API Server oficial do Holyrics na rede local.",
                    color=ft.Colors.GREY_400,
                ),
                ft.Divider(),
                ft.Card(
                    content=ft.Container(
                        padding=20,
                        content=ft.Column(
                            [
                                ft.Row([self.host_input, self.port_input]),
                                ft.Row([self.token_input, self.test_conn_button]),
                                self.conn_result_text,
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
                                        ft.Text("PLAYLIST ATIVA NO HOLYRICS", size=14, weight=ft.FontWeight.BOLD),
                                        ft.IconButton(
                                            ft.Icons.REFRESH,
                                            tooltip="Recarregar Playlist",
                                            on_click=lambda _: asyncio.create_task(self.holyrics.fetch_playlist()),
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                ft.ListView([self.playlist_table], expand=True),
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

    def _on_host_changed(self, e: ft.ControlEvent) -> None:
        self.settings.holyrics.host = e.control.value
        self.holyrics.client.host = e.control.value
        self.settings.save()

    def _on_port_changed(self, e: ft.ControlEvent) -> None:
        val = e.control.value
        if val.isdigit():
            self.settings.holyrics.port = int(val)
            self.holyrics.client.port = int(val)
            self.settings.save()

    def _on_token_changed(self, e: ft.ControlEvent) -> None:
        self.settings.holyrics.token = e.control.value
        self.holyrics.client.token = e.control.value
        self.settings.save()

    def _on_test_connection(self, _: ft.ControlEvent) -> None:
        async def _test() -> None:
            self.conn_result_text.value = "Testando conexão..."
            self.conn_result_text.color = ft.Colors.AMBER_400
            try:
                self.update()
            except (RuntimeError, Exception):
                pass

            ok = await self.holyrics.client.test_connection()
            if ok:
                self.conn_result_text.value = "Conexão estabelecida com sucesso!"
                self.conn_result_text.color = ft.Colors.GREEN_400
                await self.holyrics.fetch_playlist()
            else:
                self.conn_result_text.value = "Falha ao conectar. Verifique IP, Porta e Token."
                self.conn_result_text.color = ft.Colors.RED_400
            try:
                self.update()
            except (RuntimeError, Exception):
                pass

        asyncio.create_task(_test())

    def update_ui(self) -> None:
        rows: list[ft.DataRow] = []
        for song in self.state.playlist.songs:
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(song.id))),
                        ft.DataCell(ft.Text(song.title, weight=ft.FontWeight.W_500)),
                        ft.DataCell(ft.Text(song.artist or "—")),
                        ft.DataCell(ft.Text(str(len(song.slides)))),
                    ]
                )
            )
        self.playlist_table.rows = rows
        try:
            self.update()
        except (RuntimeError, Exception):
            pass

