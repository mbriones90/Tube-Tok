"""Modelos de dominio del cliente multimedia."""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class Video:
    video_id: str
    title: str = ""
    thumbnail_url: str = ""
    duration: float | None = None
    channel: str = ""
    webpage_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Video":
        campos = {k: data.get(k) for k in
                  ("video_id", "title", "thumbnail_url", "duration", "channel", "webpage_url")}
        return cls(**campos)


def format_duration(seconds: float | None) -> str:
    """Convierte segundos a 'mm:ss' o 'h:mm:ss'."""
    if not seconds or seconds <= 0:
        return ""
    total = int(seconds)
    horas, resto = divmod(total, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return f"{horas}:{minutos:02d}:{segundos:02d}"
    return f"{minutos}:{segundos:02d}"
