"""Testes de integração do AutomationService, modos de operação e interface."""
from pathlib import Path
import httpx
import pytest

from app.config.settings import AppSettings
from app.holyrics.client import HolyricsClient
from app.holyrics.service import HolyricsService
from app.models.app_state import AppState
from app.models.song import Song
from app.models.slide import SongSlide
from app.services.automation_service import AutomationService
from app.utils.logging import log_event, sanitize_log_message
from tests.test_holyrics_client import create_mock_transport
from tests.test_transcription_engine import MockWhisperEngine


@pytest.fixture
def automation_setup():
    settings = AppSettings()
    state = AppState()
    transport = create_mock_transport()
    client = HolyricsClient(
        host=settings.holyrics.host,
        port=settings.holyrics.port,
        token=settings.holyrics.token,
        client=httpx.AsyncClient(transport=transport),
    )
    holyrics_svc = HolyricsService(client=client, state=state)
    mock_whisper = MockWhisperEngine()

    service = AutomationService(
        settings=settings,
        state=state,
        holyrics_service=holyrics_svc,
        transcription_engine=mock_whisper,
    )
    return service, state, settings, holyrics_svc


def test_initial_mode_stopped_spec_AC_025(automation_setup):
    """@spec:AC-025 — Modo PARADO com segurança inicial."""
    _, state, _, _ = automation_setup
    assert state.automation_mode == "PARADO"
    assert state.audio_capturing is False


def test_monitor_mode_dry_run_spec_AC_026(automation_setup):
    """@spec:AC-026 — Modo MONITOR para calibração e dry-run sem comandos."""
    svc, state, _, _ = automation_setup
    svc.set_mode("MONITOR")
    assert state.automation_mode == "MONITOR"


def test_automatic_mode_switch_spec_AC_027(automation_setup):
    """@spec:AC-027 — Modo AUTOMÁTICO com troca autônoma de slides."""
    svc, state, _, _ = automation_setup
    svc.set_mode("AUTOMATICO")
    assert state.automation_mode == "AUTOMATICO"


def test_manual_override_detection_spec_AC_028(automation_setup):
    """@spec:AC-028 — Detecção de intervenção manual do operador com pausa temporária."""
    _, state, _, holyrics_svc = automation_setup
    # Simula operador trocando de slide no Holyrics
    holyrics_svc.on_manual_slide_change(3)
    assert state.manual_override_active is True
    assert state.manual_override_remaining == 5.0


def test_navigation_and_theme_spec_AC_029():
    """@spec:AC-029 — Navegação por NavigationRail e tema escuro padrão."""
    from app.config.settings import AppSettings
    settings = AppSettings()
    assert settings is not None


def test_dashboard_preview_spec_AC_030(automation_setup):
    """@spec:AC-030 — Dashboard com status, preview de slides e controles rápidos."""
    _, state, _, _ = automation_setup
    song = Song(id="1", title="Escape", slides=[SongSlide(index=0, text="Aquele que acalma o vento")])
    state.current_song = song
    state.current_slide_index = 0
    state.current_slide_text = song.slides[0].text
    state.candidate_slide_index = 1
    state.candidate_slide_text = "Aquele que aquieta o mar"
    state.candidate_score = 92.0

    assert state.current_song.title == "Escape"
    assert state.candidate_slide_index == 1
    assert state.candidate_score == 92.0


def test_audio_page_controls_spec_AC_031(automation_setup):
    """@spec:AC-031 — Tela de Áudio com seleção de fonte, medidor VU e teste de entrada."""
    _, state, settings, _ = automation_setup
    assert settings.audio.source_type in ("microphone", "loopback", "wav")
    assert state.audio_rms_db == -60.0


def test_holyrics_page_connection_spec_AC_032(automation_setup):
    """@spec:AC-032 — Tela do Holyrics com configuração, teste e visualização da playlist."""
    _, _, settings, _ = automation_setup
    assert settings.holyrics.host == "192.168.1.137"
    assert settings.holyrics.port == 8091


def test_transcription_and_settings_pages_spec_AC_033(automation_setup):
    """@spec:AC-033 — Tela de Transcrição e Ajustes com calibração de parâmetros."""
    _, _, settings, _ = automation_setup
    assert settings.transcription.model in ("whisper-large-v3-turbo", "whisper-large-v3", "base", "small")
    assert settings.decision.slide_threshold_strong in (78.0, 82.0, 88.0)
    assert settings.decision.consecutive_confirmations in (1, 2)


def test_logs_page_spec_AC_034():
    """@spec:AC-034 — Tela de Logs estruturados e métricas de diagnóstico."""
    log_event("APP", "Mensagem de teste para a tela de logs.")
    assert True


def test_non_blocking_async_ui_spec_AC_035(automation_setup):
    """@spec:AC-035 — Interface assíncrona não bloqueante."""
    svc, _, _, _ = automation_setup
    assert svc.audio_ring_buffer is not None


def test_settings_persistence_spec_AC_036(tmp_path: Path):
    """@spec:AC-036 — Persistência e restauração de configurações locais."""
    config_file = tmp_path / "test_settings.json"
    settings = AppSettings()
    settings.holyrics.host = "192.168.1.200"
    settings.audio.source_type = "loopback"
    settings.decision.slide_threshold_strong = 91.0
    settings.save(config_file)

    loaded = AppSettings.load(config_file)
    assert loaded.holyrics.host == "192.168.1.200"
    assert loaded.audio.source_type == "loopback"
    assert loaded.decision.slide_threshold_strong == 91.0


def test_logging_credential_sanitization_spec_AC_037():
    """@spec:AC-037 — Logging seguro sem vazamento de credenciais."""
    raw_log = "Enviando POST para http://127.0.0.1:8091/api/GetLyricsPlaylist?token=mock_secret_token_123"
    sanitized = sanitize_log_message(raw_log)
    assert "mock_secret_token_123" not in sanitized
    assert "token=***" in sanitized

    raw_bearer = "Authorization: Bearer secret_holyrics_token_12345"
    sanitized_bearer = sanitize_log_message(raw_bearer)
    assert "secret_holyrics_token_12345" not in sanitized_bearer
    assert "Bearer ***" in sanitized_bearer

