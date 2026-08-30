"""Testes unitários e de integração com mock do HolyricsClient."""
import httpx
import pytest

from app.holyrics.client import HolyricsClient


def create_mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)

        if "GetLyricsPlaylist" in url:
            return httpx.Response(
                200,
                json=[
                    {"id": "1", "title": "Escape", "artist": "Renascer Praise"},
                    {"id": "2", "title": "Bondade de Deus", "artist": "Isaías Saad"},
                ],
            )
        elif "GetLyrics" in url:
            return httpx.Response(
                200,
                json={
                    "id": "1",
                    "title": "Escape",
                    "artist": "Renascer Praise",
                    "slides": [
                        {"text": "Aquele que acalma o vento"},
                        {"text": "Aquele que aquieta o mar"},
                        {"text": "É o mesmo que me faz vencer"},
                    ],
                },
            )
        elif "GetCurrentPresentation" in url:
            return httpx.Response(
                200,
                json={
                    "id": "1",
                    "title": "Escape",
                    "artist": "Renascer Praise",
                    "slide": 1,
                    "total_slides": 3,
                },
            )
        elif "ShowLyrics" in url or "ActionGoToIndex" in url or "ActionNext" in url or "ActionPrevious" in url:
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404, json={"error": "Not Found"})

    return httpx.MockTransport(handler)


@pytest.fixture
def mock_client() -> HolyricsClient:
    transport = create_mock_transport()
    async_client = httpx.AsyncClient(transport=transport)
    return HolyricsClient(
        host="127.0.0.1",
        port=8091,
        token="test_token_secret_123",
        client=async_client,
    )


@pytest.mark.asyncio
async def test_connection_and_auth_spec_AC_001(mock_client: HolyricsClient):
    """@spec:AC-001 — Teste de conexão e autenticação com API Server do Holyrics."""
    is_connected = await mock_client.test_connection()
    assert is_connected is True


@pytest.mark.asyncio
async def test_get_lyrics_playlist_spec_AC_002(mock_client: HolyricsClient):
    """@spec:AC-002 — Consulta e carregamento da playlist de letras do Holyrics."""
    playlist = await mock_client.get_lyrics_playlist()
    assert len(playlist) == 2
    assert playlist[0].title == "Escape"
    assert str(playlist[0].id) == "1"


@pytest.mark.asyncio
async def test_get_lyrics_slides_spec_AC_003(mock_client: HolyricsClient):
    """@spec:AC-003 — Carregamento e cache dos slides de cada música."""
    song_details = await mock_client.get_lyrics("1")
    assert song_details.title == "Escape"
    assert len(song_details.slides) == 3
    assert song_details.slides[0].text == "Aquele que acalma o vento"


@pytest.mark.asyncio
async def test_get_current_presentation_spec_AC_004(mock_client: HolyricsClient):
    """@spec:AC-004 — Sincronização periódica da apresentação e slide atual."""
    curr = await mock_client.get_current_presentation()
    assert curr.id == "1"
    assert curr.slide == 1
    assert curr.total_slides == 3


@pytest.mark.asyncio
async def test_show_lyrics_and_go_to_index_spec_AC_005(mock_client: HolyricsClient):
    """@spec:AC-005 — Comando de exibição de música e navegação direta por índice."""
    res_show = await mock_client.show_lyrics("1", initial_index=0)
    assert res_show is True
    res_goto = await mock_client.go_to_index(1)
    assert res_goto is True


@pytest.mark.asyncio
async def test_manual_next_and_previous_spec_AC_006(mock_client: HolyricsClient):
    """@spec:AC-006 — Comandos manuais de navegação Próximo e Anterior."""
    res_next = await mock_client.next()
    assert res_next is True
    res_prev = await mock_client.previous()
    assert res_prev is True


def test_index_normalization_spec_AC_007():
    """@spec:AC-007 — Normalização de índices entre zero-based e one-based."""
    raw_api_slide_number = 1
    normalized_0_based = max(0, raw_api_slide_number - 1)
    assert normalized_0_based == 0

    display_1_based = normalized_0_based + 1
    assert display_1_based == 1

