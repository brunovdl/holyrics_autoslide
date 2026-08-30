"""Página de configuração de áudio e diagnóstico de entrada."""
from __future__ import annotations

import flet as ft
from app.models.app_state import AppState
from app.config.settings import AppSettings
from app.audio.devices import list_audio_devices
from app.services.automation_service import AutomationService


class AudioPage(ft.Container):
    """Configuração de fontes de áudio (Microfone / Loopback / WAV) e VU meter."""

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

        self.source_type_dropdown = ft.Dropdown(
            label="Tipo de Fonte",
            value=self.settings.audio.source_type,
            options=[
                ft.dropdown.Option("microphone", "Microfone / Entrada de Linha"),
                ft.dropdown.Option("loopback", "Áudio do Sistema / Loopback (Speakers)"),
                ft.dropdown.Option("wav", "Arquivo WAV de Teste"),
            ],
            on_select=self._on_source_type_changed,
            expand=True,
        )

        self.device_dropdown = ft.Dropdown(
            label="Dispositivo de Áudio",
            options=[],
            expand=True,
            on_select=self._on_device_changed,
        )

        self.wav_file_input = ft.TextField(
            label="Caminho do Arquivo WAV",
            value=self.settings.audio.wav_file_path or "",
            expand=True,
            visible=self.settings.audio.source_type == "wav",
            on_change=self._on_wav_path_changed,
        )

        self.vu_bar = ft.ProgressBar(value=0.0, height=12, color=ft.Colors.GREEN_400, bgcolor=ft.Colors.GREY_800)
        self.vu_text = ft.Text("-60.0 dB (Peak: -60.0 dB)", size=13, color=ft.Colors.GREY_300)

        self.test_button = ft.Button(
            "Testar Entrada",
            icon=ft.Icons.MIC,
            bgcolor=ft.Colors.GREEN_800,
            color=ft.Colors.WHITE,
            on_click=self._toggle_test_audio,
        )

        self.refresh_devices_button = ft.OutlinedButton(
            "Atualizar Dispositivos",
            icon=ft.Icons.REFRESH,
            on_click=lambda _: self._refresh_devices_list(),
        )

        self.content = self._build_layout()
        self._refresh_devices_list()

    def _build_layout(self) -> ft.Control:
        return ft.Column(
            [
                ft.Text("CONFIGURAÇÃO DE ÁUDIO", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Selecione o microfone ou a saída do sistema para escuta e reconhecimento contínuo.",
                    color=ft.Colors.GREY_400,
                ),
                ft.Divider(),
                ft.Card(
                    content=ft.Container(
                        padding=20,
                        content=ft.Column(
                            [
                                ft.Row([self.source_type_dropdown, self.refresh_devices_button]),
                                self.device_dropdown,
                                self.wav_file_input,
                            ],
                            spacing=15,
                        ),
                    )
                ),
                ft.Card(
                    content=ft.Container(
                        padding=20,
                        content=ft.Column(
                            [
                                ft.Text("DIAGNÓSTICO E NÍVEL DE ENTRADA", size=14, weight=ft.FontWeight.BOLD),
                                self.vu_bar,
                                ft.Row([self.vu_text, self.test_button], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ],
                            spacing=10,
                        ),
                    )
                ),
            ],
            spacing=15,
            expand=True,
        )

    def _refresh_devices_list(self) -> None:
        devices = list_audio_devices()
        options: list[ft.dropdown.Option] = []
        is_loop = self.settings.audio.source_type == "loopback"

        for dev in devices:
            if is_loop and not dev.is_loopback:
                continue
            options.append(ft.dropdown.Option(str(dev.id), f"[{dev.host_api}] {dev.name}"))

        self.device_dropdown.options = options
        if options:
            saved_id = str(self.settings.audio.device_id) if self.settings.audio.device_id is not None else options[0].key
            self.device_dropdown.value = saved_id
            self.settings.audio.device_id = int(saved_id) if saved_id.isdigit() else saved_id
        try:
            self.update()
        except (RuntimeError, Exception):
            pass

    def _on_source_type_changed(self, e: ft.ControlEvent) -> None:
        self.settings.audio.source_type = e.control.value
        self.wav_file_input.visible = e.control.value == "wav"
        self._refresh_devices_list()
        self.settings.save()
        try:
            self.update()
        except (RuntimeError, Exception):
            pass

    def _on_device_changed(self, e: ft.ControlEvent) -> None:
        val = e.control.value
        self.settings.audio.device_id = int(val) if val and val.isdigit() else val
        self.settings.save()

    def _on_wav_path_changed(self, e: ft.ControlEvent) -> None:
        self.settings.audio.wav_file_path = e.control.value
        self.settings.save()

    def _toggle_test_audio(self, _: ft.ControlEvent) -> None:
        if self.state.audio_capturing:
            self.automation.stop_audio()
            self.test_button.text = "Testar Entrada"
            self.test_button.bgcolor = ft.Colors.GREEN_800
        else:
            self.automation.start_audio()
            self.test_button.text = "Parar Teste"
            self.test_button.bgcolor = ft.Colors.RED_800
        try:
            self.update()
        except (RuntimeError, Exception):
            pass

    def update_ui(self) -> None:
        db = self.state.audio_peak_db
        rms = self.state.audio_rms_db
        normalized_vu = max(0.0, min(1.0, (db + 60.0) / 60.0))
        self.vu_bar.value = normalized_vu
        self.vu_text.value = f"RMS: {rms:.1f} dB | Peak: {db:.1f} dB"
        try:
            self.update()
        except (RuntimeError, Exception):
            pass

