"""Enumeração de dispositivos de áudio de entrada e loopback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

try:
    import sounddevice as sd
except Exception:
    sd = None


@dataclass
class AudioDeviceInfo:
    """Informações de um dispositivo de áudio."""
    id: int | str
    name: str
    host_api: str
    max_input_channels: int
    default_samplerate: float
    is_loopback: bool = False
    source_type: Literal["microphone", "loopback", "wav"] = "microphone"


def list_audio_devices() -> list[AudioDeviceInfo]:
    """Lista todos os dispositivos de entrada e loopback disponíveis no sistema."""
    if sd is None:
        return []

    devices_list: list[AudioDeviceInfo] = []
    try:
        hostapis = sd.query_hostapis()
        devices = sd.query_devices()

        for idx, dev in enumerate(devices):
            api_info = hostapis[dev["hostapi"]] if dev["hostapi"] < len(hostapis) else {}
            api_name = api_info.get("name", "Desconhecido")
            name = dev.get("name", f"Dispositivo {idx}")
            max_in = dev.get("max_input_channels", 0)
            samplerate = dev.get("default_samplerate", 44100.0)

            is_loopback = False
            if "monitor" in name.lower():
                is_loopback = True
            elif "wasapi" in api_name.lower() and ("loopback" in name.lower() or max_in > 0):
                is_loopback = True

            if max_in > 0 or is_loopback:
                devices_list.append(
                    AudioDeviceInfo(
                        id=idx,
                        name=name,
                        host_api=api_name,
                        max_input_channels=max_in,
                        default_samplerate=samplerate,
                        is_loopback=is_loopback,
                        source_type="loopback" if is_loopback else "microphone",
                    )
                )
    except Exception as e:
        print(f"Erro ao enumerar dispositivos de áudio: {e}")

    return devices_list


def get_default_device(source_type: str = "microphone") -> AudioDeviceInfo | None:
    """Retorna o dispositivo padrão recomendado para o tipo de fonte."""
    devices = list_audio_devices()
    if not devices:
        return None

    if source_type == "loopback":
        for d in devices:
            if d.is_loopback or "monitor" in d.name.lower():
                return d
        return devices[0]
    else:
        for d in devices:
            if not d.is_loopback and d.max_input_channels > 0:
                return d
        return devices[0]

