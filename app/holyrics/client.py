"""Cliente HTTP assíncrono para a API Server oficial do Holyrics."""
from __future__ import annotations

from typing import Any
import httpx

from app.holyrics.dto import (
    HolyricsCurrentPresentationDTO,
    HolyricsPlaylistItemDTO,
    HolyricsSongDetailsDTO,
)
from app.utils.logging import log_event


class HolyricsClient:
    """Cliente de comunicação HTTP com o Holyrics API Server."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8091,
        token: str = "",
        timeout: float = 2.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.timeout = timeout
        self._client = client
        self._owns_client = client is None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/api"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def reset_client(self) -> None:
        """Fecha e reinicia a sessão HTTP para evitar sockets pendentes."""
        if self._owns_client and self._client:
            try:
                if not self._client.is_closed:
                    await self._client.aclose()
            except Exception:
                pass
            self._client = None

    async def close(self) -> None:
        await self.reset_client()

    async def _post(self, action: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Executa requisição POST para a API do Holyrics."""
        url = f"{self.base_url}/{action}?token={self.token}"
        headers = {"Content-Type": "application/json"}
        client = await self._get_client()
        try:
            response = await client.post(url, json=data or {}, headers=headers)
            response.raise_for_status()
            if response.content:
                try:
                    return response.json()
                except Exception:
                    return {"status": "ok", "raw": response.text}
            return {"status": "ok"}
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException, ConnectionRefusedError, OSError) as e:
            await self.reset_client()
            raise
        except httpx.HTTPError as e:
            log_event("HOLYRICS", f"Erro na requisição {action}: {e}", level=30)
            raise

    async def test_connection(self) -> bool:
        """Testa conexão com o Holyrics via GetLyricsPlaylist ou GetCurrentPresentation."""
        try:
            await self.get_lyrics_playlist()
            return True
        except Exception:
            try:
                await self._post("GetCurrentPresentation")
                return True
            except Exception:
                return False

    async def get_lyrics_playlist(self) -> list[HolyricsPlaylistItemDTO]:
        """Consulta a playlist de letras ativas do Holyrics."""
        data = await self._post("GetLyricsPlaylist")
        items: list[Any] = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key in ["data", "playlist", "items", "songs", "list", "result"]:
                if key in data and isinstance(data[key], list):
                    items = data[key]
                    break
            else:
                items = [data] if "id" in data or "title" in data else []

        result: list[HolyricsPlaylistItemDTO] = []
        for item in items:
            if isinstance(item, dict):
                result.append(HolyricsPlaylistItemDTO.model_validate(item))
            elif isinstance(item, str):
                result.append(HolyricsPlaylistItemDTO(id=item, title=item))
        return result

    def _parse_song_details(self, data: Any, fallback_id: str = "", fallback_title: str = "", fallback_artist: str = "") -> dict[str, Any]:
        """Normaliza qualquer variante de resposta do GetLyrics para o formato esperado pelo DTO."""
        if not isinstance(data, dict):
            return {"id": fallback_id, "title": fallback_title, "artist": fallback_artist, "slides": []}

        # Desaninha se estiver dentro de chaves como data/item/song/result/presentation
        for nested_k in ["data", "item", "song", "result", "presentation"]:
            if isinstance(data.get(nested_k), dict):
                data = {**data[nested_k], **{k: v for k, v in data.items() if k != nested_k}}
                break

        song_id = str(data.get("id") or data.get("song_id") or fallback_id)
        title = str(data.get("title") or data.get("name") or fallback_title)
        artist = str(data.get("artist") or data.get("author") or fallback_artist)

        raw_slides = None
        for slide_key in ["slides", "paragraphs", "verses", "items", "list", "sections"]:
            if slide_key in data and isinstance(data[slide_key], list):
                raw_slides = data[slide_key]
                break

        extracted_slides: list[dict[str, str]] = []
        if raw_slides is not None:
            for item in raw_slides:
                if isinstance(item, str) and item.strip():
                    extracted_slides.append({"text": item.strip()})
                elif isinstance(item, dict):
                    t = ""
                    for tk in ["text", "paragraph", "content", "lyrics", "verse", "words", "body", "label"]:
                        if tk in item and item[tk]:
                            if isinstance(item[tk], list):
                                t = "\n".join(str(x) for x in item[tk] if x).strip()
                            else:
                                t = str(item[tk]).strip()
                            if t:
                                break
                    if not t and "lines" in item and isinstance(item["lines"], list):
                        t = "\n".join(str(line) for line in item["lines"] if line).strip()
                    if t:
                        extracted_slides.append({"text": t})
        else:
            for text_key in ["lyrics", "text", "full_text", "content"]:
                if text_key in data and isinstance(data[text_key], str) and data[text_key].strip():
                    parts = [p.strip() for p in data[text_key].split("\n\n") if p.strip()]
                    if parts:
                        extracted_slides = [{"text": p} for p in parts]
                        break

        return {
            "id": song_id,
            "title": title,
            "artist": artist,
            "slides": extracted_slides,
        }

    async def get_lyrics(self, song_id: str | int) -> HolyricsSongDetailsDTO:
        """Consulta os slides e detalhes de uma música específica."""
        id_str = str(song_id)
        payload: dict[str, Any] = {"id": id_str}
        data = await self._post("GetLyrics", payload)
        parsed = self._parse_song_details(data, fallback_id=id_str)
        return HolyricsSongDetailsDTO.model_validate(parsed)

    async def get_current_presentation(self) -> HolyricsCurrentPresentationDTO:
        """Consulta a apresentação atual e o slide ativo no Holyrics."""
        try:
            data = await self._post("GetCurrentPresentation")
            if isinstance(data, dict):
                item_data: dict[str, Any] = {}
                for k in ["item", "data", "presentation", "song", "current"]:
                    if isinstance(data.get(k), dict):
                        item_data = data[k]
                        break

                song_id = data.get("id") or item_data.get("id") or item_data.get("song_id") or data.get("song_id")
                title = data.get("title") or item_data.get("title") or item_data.get("name") or data.get("name")
                artist = data.get("artist") or item_data.get("artist") or item_data.get("author") or data.get("author")
                slide = data.get("slide") or item_data.get("slide") or data.get("index") or item_data.get("index")
                total_slides = data.get("total_slides") or data.get("slides_count") or item_data.get("total_slides") or item_data.get("slides_count")

                is_active = bool(song_id or title or slide is not None)
                return HolyricsCurrentPresentationDTO(
                    id=str(song_id) if song_id is not None else None,
                    title=str(title) if title is not None else None,
                    artist=str(artist) if artist is not None else None,
                    slide=int(slide) if slide is not None else None,
                    total_slides=int(total_slides) if total_slides is not None else None,
                    is_active=is_active,
                )
            return HolyricsCurrentPresentationDTO(is_active=False)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return HolyricsCurrentPresentationDTO(is_active=False)
            raise

    async def show_lyrics(self, song_id: str | int, initial_index: int | None = None) -> bool:
        """Exibe uma música no Holyrics, opcionalmente iniciando em um índice (0-based)."""
        payload: dict[str, Any] = {"id": str(song_id)}
        if initial_index is not None:
            payload["initial_index"] = int(initial_index)
            payload["index"] = int(initial_index)
        await self._post("ShowLyrics", payload)
        if initial_index is not None:
            await self.go_to_index(initial_index)
        return True

    async def go_to_index(self, index: int) -> bool:
        """Troca para o slide especificado pelo índice 0-based."""
        await self._post("ActionGoToIndex", {"index": int(index)})
        return True

    def post_sync(self, action: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Executa requisição POST síncrona segura para chamadas a partir de threads."""
        url = f"{self.base_url}/{action}?token={self.token}"
        headers = {"Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=data or {}, headers=headers)
                response.raise_for_status()
                if response.content:
                    try:
                        return response.json()
                    except Exception:
                        return {"status": "ok", "raw": response.text}
                return {"status": "ok"}
        except httpx.HTTPError as e:
            log_event("HOLYRICS", f"Erro síncrono na requisição {action}: {e}", level=30)
            raise

    def show_lyrics_sync(self, song_id: str | int, initial_index: int | None = None) -> bool:
        payload: dict[str, Any] = {"id": str(song_id)}
        if initial_index is not None:
            payload["initial_index"] = int(initial_index)
            payload["index"] = int(initial_index)
        self.post_sync("ShowLyrics", payload)
        if initial_index is not None:
            self.go_to_index_sync(initial_index)
        return True

    def go_to_index_sync(self, index: int) -> bool:
        self.post_sync("ActionGoToIndex", {"index": int(index)})
        return True

    async def next(self) -> bool:
        """Avança para o próximo slide no Holyrics."""
        await self._post("ActionNext")
        return True

    async def previous(self) -> bool:
        """Retorna para o slide anterior no Holyrics."""
        await self._post("ActionPrevious")
        return True

