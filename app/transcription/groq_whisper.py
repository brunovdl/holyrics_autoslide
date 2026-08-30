"""Motor de transcrição em nuvem via API da Groq (whisper-large-v3-turbo)."""
from __future__ import annotations

import io
import time
import wave
import httpx
import numpy as np

from app.models.transcription import TranscriptionResult, TranscriptionSegment
from app.utils.logging import log_event


class GroqWhisperTranscriber:
    """Cliente de transcrição ultra-rápida via API Cloud da Groq."""

    def __init__(
        self,
        api_key: str,
        model: str = "whisper-large-v3-turbo",
        base_url: str = "https://api.groq.com/openai/v1",
        language: str = "pt",
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.language = language
        self.timeout = timeout
        self._is_ready = False
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        """Fecha a sessão HTTP persistente."""
        if self._client and not self._client.is_closed:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def load_model(self) -> None:
        """Valida a configuração da API da Groq."""
        if not self.api_key or not self.api_key.strip():
            log_event("ASR", "Chave GROQ_API_KEY não informada.", level=30)
            self._is_ready = False
            return

        self._is_ready = True
        log_event(
            "ASR",
            f"Transcrição Groq Cloud ativa (modelo={self.model}, language={self.language}).",
        )

    def is_ready(self) -> bool:
        return self._is_ready

    def _audio_to_wav_bytes(self, audio: np.ndarray, sample_rate: int = 16000) -> bytes:
        """Converte array numpy float32 para formato WAV 16-bit PCM em memória."""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Converte float32 [-1.0, 1.0] para int16 PCM
        audio_int16 = (audio * 32767.0).clip(-32768, 32767).astype(np.int16)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())

        return buf.getvalue()

    def _clean_hallucinations(self, text: str) -> str:
        """Remove repetições anômalas e artefatos de alucinação gerados pelo Whisper."""
        if not text:
            return ""
        words = text.split()
        if len(words) > 6:
            for seq_len in (4, 3, 2):
                cleaned_words: list[str] = []
                i = 0
                while i < len(words):
                    chunk = words[i : i + seq_len]
                    cleaned_words.extend(chunk)
                    i += seq_len
                    while i + seq_len <= len(words) and words[i : i + seq_len] == chunk:
                        i += seq_len
                words = cleaned_words
            text = " ".join(words)
        return text.strip()

    def transcribe(self, audio: np.ndarray, prompt: str | None = None) -> TranscriptionResult:
        """Envia o chunk de áudio para a API da Groq reutilizando conexão HTTP persistente."""
        if not self._is_ready:
            self.load_model()
            if not self._is_ready:
                return TranscriptionResult(text="", duration=0.0)

        if len(audio) == 0:
            return TranscriptionResult(text="", duration=0.0)

        duration = len(audio) / 16000.0
        wav_bytes = self._audio_to_wav_bytes(audio, sample_rate=16000)

        url = f"{self.base_url}/audio/transcriptions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        data: dict[str, Any] = {
            "model": self.model,
            "language": self.language if self.language != "auto" else "pt",
            "temperature": "0.0",
            "response_format": "json",
        }
        if prompt and prompt.strip():
            data["prompt"] = prompt.strip()[:240]

        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav"),
        }

        t0 = time.time()
        try:
            client = self._get_client()
            response = client.post(url, headers=headers, data=data, files=files)
            response.raise_for_status()
            res_data = response.json()
            raw_text = res_data.get("text", "").strip()
            text = self._clean_hallucinations(raw_text)

            inference_time = (time.time() - t0) * 1000.0
            return TranscriptionResult(
                text=text,
                duration=duration,
                inference_time=round(inference_time, 1),
                segments=[TranscriptionSegment(text=text, start=0.0, end=duration)],
            )
        except httpx.HTTPStatusError as e:
            elapsed = (time.time() - t0) * 1000.0
            log_event(
                "ASR",
                f"Erro na API Groq ({e.response.status_code}): {e.response.text}",
                level=30,
            )
            return TranscriptionResult(text="", duration=duration, inference_time=round(elapsed, 1))
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException, ConnectionRefusedError, OSError) as e:
            self.close()
            elapsed = (time.time() - t0) * 1000.0
            log_event("ASR", f"Falha de conexão Groq (sessão reiniciada): {e}", level=30)
            return TranscriptionResult(text="", duration=duration, inference_time=round(elapsed, 1))
        except Exception as e:
            elapsed = (time.time() - t0) * 1000.0
            log_event("ASR", f"Falha na requisição Groq: {e}", level=30)
            return TranscriptionResult(text="", duration=duration, inference_time=round(elapsed, 1))

